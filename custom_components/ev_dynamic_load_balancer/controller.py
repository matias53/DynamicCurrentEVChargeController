"""Pure control logic for the EV Dynamic Load Balancer.

This module is deliberately independent from Home Assistant.  The controller
receives plain Python values (powers in Watts, currents in Amps, monotonic
timestamps in seconds) and returns :class:`ControlDecision` objects describing
what should happen.  All Home Assistant specific concerns (reading entity
states, calling services, firing events) live in ``coordinator.py``.

Keeping the algorithm free of framework dependencies makes it trivially unit
testable and reusable.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from enum import StrEnum
import math
from typing import Any, Final

# Charger power must move by at least this many Watts (compared with the power
# measured when a command was issued) before the charger is considered to have
# reacted to the last written current.
RESPONSE_POWER_CHANGE_W: Final[float] = 100.0

# Tolerance used when comparing two current values for equality.
CURRENT_EPSILON: Final[float] = 1e-3


class Phases(StrEnum):
    """Supported electrical installations."""

    SINGLE = "single"
    THREE = "three"

    @property
    def factor(self) -> float:
        """Return the power conversion factor (W = factor * V * A)."""
        return math.sqrt(3.0) if self is Phases.THREE else 1.0


class ControlAction(StrEnum):
    """What the caller should do with a decision."""

    NONE = "none"
    SET_CURRENT = "set_current"


class Reason(StrEnum):
    """Why the controller made (or skipped) a decision."""

    NOT_CHARGING = "not_charging"
    INVALID_INPUT = "invalid_input"
    AWAITING_RESPONSE = "awaiting_response"
    WITHIN_DEADBAND = "within_deadband"
    NO_CHANGE = "no_change"
    RATE_LIMITED = "rate_limited"
    ADJUSTMENT = "adjustment"
    EMERGENCY = "emergency"
    EMERGENCY_AT_MINIMUM = "emergency_at_minimum"


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Static configuration of the controller.

    All power values are Watts, currents are Amps, durations are seconds.
    """

    target_power: float
    emergency_power: float
    voltage: float = 230.0
    phases: Phases = Phases.SINGLE
    min_current: float = 6.0
    max_current: float = 32.0
    deadband: float = 300.0
    max_step: float = 2.0
    gain: float = 0.5
    average_window: float = 30.0
    response_timeout: float = 15.0
    min_change_interval: float = 10.0
    emergency_reduction: float = 6.0
    current_step: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration invariants."""
        if self.target_power <= 0:
            raise ValueError("target_power must be positive")
        if self.emergency_power <= self.target_power:
            raise ValueError("emergency_power must be greater than target_power")
        if self.voltage <= 0:
            raise ValueError("voltage must be positive")
        if self.min_current < 0:
            raise ValueError("min_current must not be negative")
        if self.max_current <= self.min_current:
            raise ValueError("max_current must be greater than min_current")
        if self.deadband < 0:
            raise ValueError("deadband must not be negative")
        if self.max_step <= 0:
            raise ValueError("max_step must be positive")
        if self.gain <= 0:
            raise ValueError("gain must be positive")
        if self.average_window <= 0:
            raise ValueError("average_window must be positive")
        if self.response_timeout < 0:
            raise ValueError("response_timeout must not be negative")
        if self.min_change_interval < 0:
            raise ValueError("min_change_interval must not be negative")
        if self.emergency_reduction <= 0:
            raise ValueError("emergency_reduction must be positive")
        if self.current_step <= 0:
            raise ValueError("current_step must be positive")

    @property
    def watts_per_amp(self) -> float:
        """Return how many Watts one Amp represents for this installation."""
        return self.phases.factor * self.voltage


@dataclass(frozen=True, slots=True)
class ControllerInputs:
    """Snapshot of the world handed to the controller for one cycle."""

    now: float
    """Monotonic timestamp in seconds."""

    charging: bool
    """Whether the vehicle is currently charging."""

    grid_power: float | None
    """Instantaneous imported grid power in Watts (``None`` if unavailable)."""

    charger_power: float | None
    """Instantaneous charger power in Watts (``None`` if unavailable)."""

    actual_current: float | None
    """Currently configured charging current in Amps (``None`` if unavailable)."""


@dataclass(frozen=True, slots=True)
class ControlDecision:
    """The outcome of one controller cycle."""

    action: ControlAction
    reason: Reason
    emergency: bool = False
    new_current: float | None = None
    previous_current: float | None = None
    error: float | None = None
    average_power: float | None = None
    delta_raw: float | None = None
    delta_limited: float | None = None
    sample_count: int = 0


@dataclass(frozen=True, slots=True)
class _PendingCommand:
    """A current change that was written and is awaiting charger response."""

    sent_at: float
    target_current: float
    charger_power_at_send: float | None


@dataclass(slots=True)
class ControllerStats:
    """Runtime counters, exposed through diagnostics."""

    cycles: int = 0
    commands_sent: int = 0
    emergencies: int = 0
    response_timeouts: int = 0
    reasons: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable representation."""
        return {
            "cycles": self.cycles,
            "commands_sent": self.commands_sent,
            "emergencies": self.emergencies,
            "response_timeouts": self.response_timeouts,
            "reasons": dict(self.reasons),
        }


class LoadBalanceController:
    """Proportional feedback controller with hysteresis and rate limiting.

    The controller keeps a time based moving average of the grid power and,
    every cycle, decides whether the charging current should be changed and by
    how much.  It never talks to Home Assistant directly.
    """

    def __init__(self, config: ControllerConfig) -> None:
        """Initialize the controller with a validated configuration."""
        self._config = config
        self._samples: deque[tuple[float, float]] = deque()
        self._last_change: float | None = None
        self._pending: _PendingCommand | None = None
        self._last_decision: ControlDecision | None = None
        self._stats = ControllerStats()

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    @property
    def config(self) -> ControllerConfig:
        """Return the active configuration."""
        return self._config

    @property
    def last_decision(self) -> ControlDecision | None:
        """Return the most recent decision, if any."""
        return self._last_decision

    @property
    def stats(self) -> ControllerStats:
        """Return runtime statistics."""
        return self._stats

    @property
    def awaiting_response(self) -> bool:
        """Return True while a written command awaits a charger reaction."""
        return self._pending is not None

    def update_config(self, config: ControllerConfig) -> None:
        """Replace the configuration (buffer is pruned lazily)."""
        self._config = config

    # ------------------------------------------------------------------
    # Moving average
    # ------------------------------------------------------------------
    def add_sample(self, now: float, power: float) -> None:
        """Record a grid power sample and drop samples outside the window."""
        self._samples.append((now, power))
        self._prune(now)

    def average(self, now: float) -> float | None:
        """Return the moving average of grid power, or None when empty."""
        self._prune(now)
        if not self._samples:
            return None
        return sum(power for _, power in self._samples) / len(self._samples)

    def reset_average(self) -> None:
        """Discard all buffered samples."""
        self._samples.clear()

    def _prune(self, now: float) -> None:
        """Drop samples older than the configured averaging window."""
        window = self._config.average_window
        while self._samples and now - self._samples[0][0] > window:
            self._samples.popleft()

    # ------------------------------------------------------------------
    # Command bookkeeping
    # ------------------------------------------------------------------
    def command_sent(
        self, now: float, new_current: float, charger_power: float | None
    ) -> None:
        """Record that a current change has been written to the charger."""
        self._last_change = now
        self._pending = _PendingCommand(
            sent_at=now,
            target_current=new_current,
            charger_power_at_send=charger_power,
        )
        self._stats.commands_sent += 1

    def clear_pending(self) -> None:
        """Forget any pending command (e.g. when charging stops)."""
        self._pending = None

    # ------------------------------------------------------------------
    # Main algorithm
    # ------------------------------------------------------------------
    def compute(self, inputs: ControllerInputs) -> ControlDecision:
        """Run one controller cycle and return the decision.

        The caller is responsible for actually writing ``new_current`` to the
        charger and, on success, calling :meth:`command_sent`.
        """
        cfg = self._config
        self._stats.cycles += 1

        # 1. Vehicle not charging -> nothing to control.
        if not inputs.charging:
            self._pending = None
            return self._decide(ControlAction.NONE, Reason.NOT_CHARGING)

        # 3. Reject invalid states (unknown / unavailable / None).
        if inputs.grid_power is None or inputs.actual_current is None:
            return self._decide(ControlAction.NONE, Reason.INVALID_INPUT)

        # Feed the moving average with the raw grid power sample.
        self.add_sample(inputs.now, inputs.grid_power)
        average = self.average(inputs.now)
        assert average is not None  # a sample was just added
        error = cfg.target_power - average
        samples = len(self._samples)

        # Emergency mode uses the *instantaneous* grid power and bypasses the
        # proportional controller, deadband and rate limiting entirely.
        if inputs.grid_power > cfg.emergency_power:
            self._stats.emergencies += 1
            reduced = self._clamp(
                self._quantize(inputs.actual_current - cfg.emergency_reduction)
            )
            if reduced < inputs.actual_current - CURRENT_EPSILON:
                self._pending = None
                return self._decide(
                    ControlAction.SET_CURRENT,
                    Reason.EMERGENCY,
                    emergency=True,
                    new_current=reduced,
                    previous_current=inputs.actual_current,
                    error=error,
                    average_power=average,
                    sample_count=samples,
                )
            # Already at (or below) the minimum current: nothing left to shed.
            return self._decide(
                ControlAction.NONE,
                Reason.EMERGENCY_AT_MINIMUM,
                emergency=True,
                previous_current=inputs.actual_current,
                error=error,
                average_power=average,
                sample_count=samples,
            )

        # 13. Wait until the charger power changes OR the response timeout
        # expires before issuing another command.
        if self._pending is not None:
            pending = self._pending
            elapsed = inputs.now - pending.sent_at
            responded = (
                inputs.charger_power is not None
                and pending.charger_power_at_send is not None
                and abs(inputs.charger_power - pending.charger_power_at_send)
                >= RESPONSE_POWER_CHANGE_W
            )
            if responded:
                self._pending = None
            elif elapsed >= cfg.response_timeout:
                self._pending = None
                self._stats.response_timeouts += 1
            else:
                return self._decide(
                    ControlAction.NONE,
                    Reason.AWAITING_RESPONSE,
                    previous_current=inputs.actual_current,
                    error=error,
                    average_power=average,
                    sample_count=samples,
                )

        # Hysteresis: inside the deadband, do nothing.
        if abs(error) <= cfg.deadband:
            return self._decide(
                ControlAction.NONE,
                Reason.WITHIN_DEADBAND,
                previous_current=inputs.actual_current,
                error=error,
                average_power=average,
                sample_count=samples,
            )

        # 5-7. Proportional term: Watts -> Amps, apply gain, limit the step.
        delta_raw = (error / cfg.watts_per_amp) * cfg.gain
        delta_limited = max(-cfg.max_step, min(cfg.max_step, delta_raw))

        # 8-9. New setpoint, clamped to the configured current limits.
        new_current = self._clamp(self._quantize(inputs.actual_current + delta_limited))

        # 10. Quantization / clamping may cancel the change entirely.
        if abs(new_current - inputs.actual_current) < CURRENT_EPSILON:
            return self._decide(
                ControlAction.NONE,
                Reason.NO_CHANGE,
                previous_current=inputs.actual_current,
                error=error,
                average_power=average,
                delta_raw=delta_raw,
                delta_limited=delta_limited,
                sample_count=samples,
            )

        # 11. Respect the minimum time between consecutive changes.
        if (
            self._last_change is not None
            and inputs.now - self._last_change < cfg.min_change_interval
        ):
            return self._decide(
                ControlAction.NONE,
                Reason.RATE_LIMITED,
                previous_current=inputs.actual_current,
                error=error,
                average_power=average,
                delta_raw=delta_raw,
                delta_limited=delta_limited,
                sample_count=samples,
            )

        # 12. Ask the caller to write the new current.
        return self._decide(
            ControlAction.SET_CURRENT,
            Reason.ADJUSTMENT,
            new_current=new_current,
            previous_current=inputs.actual_current,
            error=error,
            average_power=average,
            delta_raw=delta_raw,
            delta_limited=delta_limited,
            sample_count=samples,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _clamp(self, current: float) -> float:
        """Clamp a current to the configured [min, max] range."""
        return max(self._config.min_current, min(self._config.max_current, current))

    def _quantize(self, current: float) -> float:
        """Round a current to the nearest multiple of ``current_step``."""
        step = self._config.current_step
        return round(round(current / step) * step, 3)

    def _decide(
        self,
        action: ControlAction,
        reason: Reason,
        **kwargs: Any,
    ) -> ControlDecision:
        """Build, record and return a decision."""
        decision = ControlDecision(action=action, reason=reason, **kwargs)
        self._last_decision = decision
        self._stats.reasons[reason.value] += 1
        return decision

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Return a JSON serializable snapshot for diagnostics."""
        return {
            "config": asdict(self._config),
            "buffer": [
                {"timestamp": timestamp, "power": power}
                for timestamp, power in self._samples
            ],
            "last_change_monotonic": self._last_change,
            "pending_command": asdict(self._pending) if self._pending else None,
            "last_decision": asdict(self._last_decision)
            if self._last_decision
            else None,
            "stats": self._stats.as_dict(),
        }
