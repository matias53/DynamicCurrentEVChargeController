"""Unit tests for the pure load balance controller.

These tests exercise the algorithm without any Home Assistant dependency.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from custom_components.ev_dynamic_load_balancer.controller import (
    RESPONSE_POWER_CHANGE_W,
    ControlAction,
    ControllerConfig,
    ControllerInputs,
    LoadBalanceController,
    Phases,
    Reason,
)

VOLTAGE = 230.0


def make_config(**overrides: Any) -> ControllerConfig:
    """Return a config with test friendly defaults."""
    defaults: dict[str, Any] = {
        "target_power": 7000.0,
        "emergency_power": 8500.0,
        "voltage": VOLTAGE,
        "phases": Phases.SINGLE,
        "min_current": 6.0,
        "max_current": 32.0,
        "deadband": 300.0,
        "max_step": 2.0,
        "gain": 1.0,
        "average_window": 30.0,
        "response_timeout": 15.0,
        "min_change_interval": 10.0,
        "emergency_reduction": 6.0,
        "current_step": 1.0,
    }
    defaults.update(overrides)
    return ControllerConfig(**defaults)


def make_inputs(
    *,
    now: float = 0.0,
    charging: bool = True,
    grid_power: float | None = 7000.0,
    charger_power: float | None = 3000.0,
    actual_current: float | None = 16.0,
) -> ControllerInputs:
    """Build controller inputs with sensible defaults."""
    return ControllerInputs(
        now=now,
        charging=charging,
        grid_power=grid_power,
        charger_power=charger_power,
        actual_current=actual_current,
    )


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_power": -1.0},
        {"emergency_power": 6000.0},  # below target
        {"voltage": 0.0},
        {"min_current": -1.0},
        {"max_current": 5.0},  # below min
        {"deadband": -1.0},
        {"max_step": 0.0},
        {"gain": 0.0},
        {"average_window": 0.0},
        {"response_timeout": -1.0},
        {"min_change_interval": -1.0},
        {"emergency_reduction": 0.0},
        {"current_step": 0.0},
    ],
)
def test_invalid_config_rejected(overrides: dict[str, Any]) -> None:
    """Invalid configuration values must raise ValueError."""
    with pytest.raises(ValueError):
        make_config(**overrides)


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------


def test_not_charging_skips() -> None:
    """When the vehicle is not charging the controller does nothing."""
    controller = LoadBalanceController(make_config())
    decision = controller.compute(make_inputs(charging=False, grid_power=99999.0))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.NOT_CHARGING
    # The grid sample is still recorded and reported.
    assert decision.average_power == pytest.approx(99999.0)


def test_average_stays_warm_while_not_charging() -> None:
    """Grid power is sampled even while idle, so the average is pre-warmed."""
    controller = LoadBalanceController(make_config(min_change_interval=0.0))
    for second in range(3):
        idle = controller.compute(
            make_inputs(now=float(second), charging=False, grid_power=7000.0)
        )
    assert idle.reason is Reason.NOT_CHARGING
    assert idle.average_power == pytest.approx(7000.0)

    # The first charging cycle immediately acts on the smoothed average
    # instead of a single raw sample.
    first = controller.compute(
        make_inputs(now=3.0, grid_power=8200.0, actual_current=16.0)
    )
    assert first.sample_count == 4
    assert first.average_power == pytest.approx((7000.0 * 3 + 8200.0) / 4)
    # Average = 7300 -> error -300, inside the deadband: the idle samples
    # prevented an overreaction to the 8200 W spike.
    assert first.reason is Reason.WITHIN_DEADBAND


def test_not_charging_without_grid_power_has_no_average() -> None:
    """Idle cycles with an unavailable grid sensor report no average."""
    controller = LoadBalanceController(make_config())
    decision = controller.compute(make_inputs(charging=False, grid_power=None))
    assert decision.reason is Reason.NOT_CHARGING
    assert decision.average_power is None


def test_invalid_grid_power_skips() -> None:
    """Unavailable grid power must abort the cycle."""
    controller = LoadBalanceController(make_config())
    decision = controller.compute(make_inputs(grid_power=None))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.INVALID_INPUT


def test_invalid_current_skips() -> None:
    """Unavailable actual current must abort the cycle."""
    controller = LoadBalanceController(make_config())
    decision = controller.compute(make_inputs(actual_current=None))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.INVALID_INPUT


# ---------------------------------------------------------------------------
# Proportional controller — single phase
# ---------------------------------------------------------------------------


def test_single_phase_increase() -> None:
    """With headroom the current is increased proportionally."""
    # Error = 7000 - 6540 = 460 W -> 2 A at 230 V, gain 1.
    controller = LoadBalanceController(make_config(gain=1.0, max_step=5.0))
    decision = controller.compute(make_inputs(grid_power=6540.0, actual_current=16.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.reason is Reason.ADJUSTMENT
    assert decision.new_current == pytest.approx(18.0)
    assert decision.delta_raw == pytest.approx(2.0)


def test_single_phase_decrease() -> None:
    """Above target the current is reduced proportionally."""
    # Error = 7000 - 7460 = -460 W -> -2 A.
    controller = LoadBalanceController(make_config(gain=1.0, max_step=5.0))
    decision = controller.compute(make_inputs(grid_power=7460.0, actual_current=16.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.new_current == pytest.approx(14.0)


def test_three_phase_conversion() -> None:
    """Three phase installations divide by sqrt(3) * voltage."""
    error = 2.0 * math.sqrt(3.0) * VOLTAGE  # exactly +2 A three phase
    controller = LoadBalanceController(
        make_config(phases=Phases.THREE, gain=1.0, max_step=5.0)
    )
    decision = controller.compute(
        make_inputs(grid_power=7000.0 - error, actual_current=16.0)
    )
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.delta_raw == pytest.approx(2.0)
    assert decision.new_current == pytest.approx(18.0)


def test_gain_scales_delta() -> None:
    """The proportional gain scales the raw delta."""
    # Error = 920 W -> 4 A raw; gain 0.5 -> 2 A.
    controller = LoadBalanceController(make_config(gain=0.5, max_step=10.0))
    decision = controller.compute(make_inputs(grid_power=6080.0, actual_current=16.0))
    assert decision.delta_raw == pytest.approx(2.0)
    assert decision.new_current == pytest.approx(18.0)


def test_negative_grid_power_increases_current() -> None:
    """Solar export (negative grid power) raises the charging current."""
    # Average = -2000 W (exporting) -> error 9000 W -> raw delta huge,
    # limited to +max_step.
    controller = LoadBalanceController(make_config(gain=1.0, max_step=2.0))
    decision = controller.compute(make_inputs(grid_power=-2000.0, actual_current=16.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.error == pytest.approx(9000.0)
    assert decision.delta_limited == pytest.approx(2.0)
    assert decision.new_current == pytest.approx(18.0)


def test_zero_target_power_allowed() -> None:
    """A 0 W target (surplus-only charging) is a valid configuration."""
    controller = LoadBalanceController(
        make_config(target_power=0.0, emergency_power=500.0, gain=1.0, max_step=5.0)
    )
    # Importing 460 W -> error -460 -> reduce by 2 A.
    decision = controller.compute(make_inputs(grid_power=460.0, actual_current=16.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.new_current == pytest.approx(14.0)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def test_max_step_limits_change() -> None:
    """A large error is limited to max_step Amps per cycle."""
    # Error = 2300 W -> 10 A raw, limited to 2 A.
    controller = LoadBalanceController(make_config(gain=1.0, max_step=2.0))
    decision = controller.compute(make_inputs(grid_power=4700.0, actual_current=16.0))
    assert decision.delta_raw == pytest.approx(10.0)
    assert decision.delta_limited == pytest.approx(2.0)
    assert decision.new_current == pytest.approx(18.0)


def test_clamped_to_max_current() -> None:
    """The new current never exceeds max_current."""
    controller = LoadBalanceController(make_config(gain=1.0, max_step=10.0))
    decision = controller.compute(make_inputs(grid_power=3000.0, actual_current=31.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.new_current == pytest.approx(32.0)


def test_clamped_to_min_current() -> None:
    """The new current never goes below min_current."""
    controller = LoadBalanceController(make_config(gain=1.0, max_step=10.0))
    decision = controller.compute(make_inputs(grid_power=8400.0, actual_current=7.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.new_current == pytest.approx(6.0)


def test_no_change_when_already_at_limit() -> None:
    """Clamping that cancels the change results in a skip."""
    controller = LoadBalanceController(make_config(gain=1.0, max_step=10.0))
    decision = controller.compute(make_inputs(grid_power=3000.0, actual_current=32.0))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.NO_CHANGE


# ---------------------------------------------------------------------------
# Deadband / hysteresis
# ---------------------------------------------------------------------------


def test_within_deadband_skips() -> None:
    """Small errors inside the deadband produce no change."""
    controller = LoadBalanceController(make_config(deadband=300.0))
    decision = controller.compute(make_inputs(grid_power=7250.0, actual_current=16.0))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.WITHIN_DEADBAND


def test_just_outside_deadband_acts() -> None:
    """Errors just outside the deadband trigger an adjustment."""
    controller = LoadBalanceController(make_config(deadband=300.0, gain=2.0))
    decision = controller.compute(make_inputs(grid_power=7400.0, actual_current=16.0))
    assert decision.action is ControlAction.SET_CURRENT


# ---------------------------------------------------------------------------
# Moving average
# ---------------------------------------------------------------------------


def test_moving_average_smooths_spikes() -> None:
    """The controller acts on the averaged power, not on single spikes."""
    controller = LoadBalanceController(
        make_config(average_window=30.0, deadband=300.0, min_change_interval=0.0)
    )
    # Three samples at target, then one spike below emergency threshold.
    for second in range(3):
        controller.compute(
            make_inputs(now=float(second), grid_power=7000.0, actual_current=16.0)
        )
    decision = controller.compute(
        make_inputs(now=3.0, grid_power=8200.0, actual_current=16.0)
    )
    # Average = (7000*3 + 8200) / 4 = 7300 -> error -300, inside deadband.
    assert decision.average_power == pytest.approx(7300.0)
    assert decision.reason is Reason.WITHIN_DEADBAND


def test_moving_average_window_expires_old_samples() -> None:
    """Samples older than the window are discarded."""
    controller = LoadBalanceController(make_config(average_window=10.0))
    controller.add_sample(0.0, 100.0)
    controller.add_sample(5.0, 200.0)
    controller.add_sample(20.0, 300.0)  # evicts both earlier samples
    assert controller.average(20.0) == pytest.approx(300.0)


def test_reset_average_clears_buffer() -> None:
    """reset_average discards all samples."""
    controller = LoadBalanceController(make_config())
    controller.add_sample(0.0, 5000.0)
    controller.reset_average()
    assert controller.average(0.0) is None


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_minimum_time_between_changes() -> None:
    """A second change within min_change_interval is rejected."""
    controller = LoadBalanceController(
        make_config(gain=1.0, min_change_interval=10.0, response_timeout=0.0)
    )
    first = controller.compute(make_inputs(now=0.0, grid_power=6000.0))
    assert first.action is ControlAction.SET_CURRENT
    controller.command_sent(0.0, first.new_current or 0.0, 3000.0)

    # 5 seconds later (timeout=0 so no pending wait): rate limited.
    second = controller.compute(make_inputs(now=5.0, grid_power=6000.0))
    assert second.action is ControlAction.NONE
    assert second.reason is Reason.RATE_LIMITED

    # 11 seconds later: allowed again.
    third = controller.compute(make_inputs(now=11.0, grid_power=6000.0))
    assert third.action is ControlAction.SET_CURRENT


# ---------------------------------------------------------------------------
# Response timeout
# ---------------------------------------------------------------------------


def test_awaiting_response_until_power_changes() -> None:
    """After a write the controller waits for the charger power to move."""
    controller = LoadBalanceController(
        make_config(gain=1.0, min_change_interval=0.0, response_timeout=15.0)
    )
    first = controller.compute(
        make_inputs(now=0.0, grid_power=6000.0, charger_power=3000.0)
    )
    assert first.action is ControlAction.SET_CURRENT
    controller.command_sent(0.0, first.new_current or 0.0, 3000.0)

    # Charger power unchanged -> still waiting.
    waiting = controller.compute(
        make_inputs(now=5.0, grid_power=6000.0, charger_power=3000.0)
    )
    assert waiting.reason is Reason.AWAITING_RESPONSE
    assert controller.awaiting_response

    # Charger power moved by more than the detection threshold -> proceed.
    moved = controller.compute(
        make_inputs(
            now=6.0,
            grid_power=6000.0,
            charger_power=3000.0 + RESPONSE_POWER_CHANGE_W + 1.0,
        )
    )
    assert moved.action is ControlAction.SET_CURRENT
    assert not controller.awaiting_response


def test_response_timeout_expires() -> None:
    """The pending state is dropped once the timeout expires."""
    controller = LoadBalanceController(
        make_config(gain=1.0, min_change_interval=0.0, response_timeout=15.0)
    )
    first = controller.compute(
        make_inputs(now=0.0, grid_power=6000.0, charger_power=3000.0)
    )
    controller.command_sent(0.0, first.new_current or 0.0, 3000.0)

    # Charger never reacted, but the timeout has passed.
    decision = controller.compute(
        make_inputs(now=16.0, grid_power=6000.0, charger_power=3000.0)
    )
    assert decision.action is ControlAction.SET_CURRENT
    assert controller.stats.response_timeouts == 1


# ---------------------------------------------------------------------------
# Emergency mode
# ---------------------------------------------------------------------------


def test_emergency_reduces_immediately() -> None:
    """Above the emergency threshold the reduction is instantaneous."""
    controller = LoadBalanceController(make_config(emergency_reduction=6.0))
    decision = controller.compute(make_inputs(grid_power=9000.0, actual_current=20.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.reason is Reason.EMERGENCY
    assert decision.emergency
    assert decision.new_current == pytest.approx(14.0)


def test_emergency_ignores_rate_limit() -> None:
    """Emergency reductions bypass min_change_interval."""
    controller = LoadBalanceController(
        make_config(gain=1.0, min_change_interval=60.0, response_timeout=0.0)
    )
    first = controller.compute(make_inputs(now=0.0, grid_power=6000.0))
    controller.command_sent(0.0, first.new_current or 0.0, 3000.0)

    # One second later the grid spikes above the emergency threshold.
    emergency = controller.compute(
        make_inputs(now=1.0, grid_power=9000.0, actual_current=18.0)
    )
    assert emergency.action is ControlAction.SET_CURRENT
    assert emergency.reason is Reason.EMERGENCY


def test_emergency_ignores_pending_response() -> None:
    """Emergency reductions bypass the awaiting-response state."""
    controller = LoadBalanceController(
        make_config(gain=1.0, min_change_interval=0.0, response_timeout=60.0)
    )
    first = controller.compute(
        make_inputs(now=0.0, grid_power=6000.0, charger_power=3000.0)
    )
    controller.command_sent(0.0, first.new_current or 0.0, 3000.0)
    assert controller.awaiting_response

    emergency = controller.compute(
        make_inputs(
            now=1.0, grid_power=9500.0, charger_power=3000.0, actual_current=18.0
        )
    )
    assert emergency.reason is Reason.EMERGENCY


def test_emergency_clamps_to_minimum() -> None:
    """The emergency reduction never goes below min_current."""
    controller = LoadBalanceController(
        make_config(min_current=6.0, emergency_reduction=10.0)
    )
    decision = controller.compute(make_inputs(grid_power=9000.0, actual_current=8.0))
    assert decision.new_current == pytest.approx(6.0)


def test_emergency_at_minimum_skips() -> None:
    """At the minimum current there is nothing left to shed."""
    controller = LoadBalanceController(make_config(min_current=6.0))
    decision = controller.compute(make_inputs(grid_power=9000.0, actual_current=6.0))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.EMERGENCY_AT_MINIMUM
    assert decision.emergency


# ---------------------------------------------------------------------------
# Quantization
# ---------------------------------------------------------------------------


def test_current_quantized_to_step() -> None:
    """The computed current is rounded to the configured resolution."""
    # Error = 350 W -> ~1.52 A raw at gain 1.
    controller = LoadBalanceController(
        make_config(gain=1.0, deadband=100.0, current_step=1.0, max_step=5.0)
    )
    decision = controller.compute(make_inputs(grid_power=6650.0, actual_current=16.0))
    assert decision.action is ControlAction.SET_CURRENT
    assert decision.new_current == pytest.approx(18.0)  # 17.52 rounded to 18


def test_sub_amp_quantization() -> None:
    """Fractional current steps are supported."""
    controller = LoadBalanceController(
        make_config(gain=1.0, deadband=100.0, current_step=0.5, max_step=5.0)
    )
    decision = controller.compute(make_inputs(grid_power=6650.0, actual_current=16.0))
    assert decision.new_current == pytest.approx(17.5)


def test_quantization_cancels_tiny_change() -> None:
    """A delta smaller than half the step results in no change."""
    # Error = 301 W (just outside deadband) -> 0.13 A at gain 0.1.
    controller = LoadBalanceController(
        make_config(gain=0.1, deadband=300.0, current_step=1.0)
    )
    decision = controller.compute(make_inputs(grid_power=6699.0, actual_current=16.0))
    assert decision.action is ControlAction.NONE
    assert decision.reason is Reason.NO_CHANGE


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_stats_and_snapshot() -> None:
    """Runtime statistics and diagnostics snapshots are consistent."""
    controller = LoadBalanceController(make_config())
    controller.compute(make_inputs(charging=False))
    controller.compute(make_inputs(grid_power=9000.0, actual_current=20.0))

    stats = controller.stats
    assert stats.cycles == 2
    assert stats.emergencies == 1
    assert stats.reasons[Reason.NOT_CHARGING.value] == 1

    snapshot = controller.snapshot()
    assert snapshot["stats"]["cycles"] == 2
    assert snapshot["config"]["target_power"] == 7000.0
    # Both cycles sampled the grid power (also while not charging).
    assert len(snapshot["buffer"]) == 2
