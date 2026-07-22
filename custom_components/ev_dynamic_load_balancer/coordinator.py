"""Coordinator bridging Home Assistant and the pure load balance controller."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_AVERAGE_GRID_POWER,
    ATTR_EMERGENCY,
    ATTR_ENTRY_ID,
    ATTR_GRID_POWER,
    ATTR_NEW_CURRENT,
    ATTR_OLD_CURRENT,
    ATTR_REASON,
    CONF_AVERAGE_WINDOW,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGING_CURRENT_ENTITY,
    CONF_CHARGING_STATUS_ENTITY,
    CONF_CURRENT_STEP,
    CONF_DEADBAND,
    CONF_EMERGENCY_POWER,
    CONF_EMERGENCY_REDUCTION,
    CONF_GAIN,
    CONF_GRID_POWER_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MAX_STEP,
    CONF_MIN_CHANGE_INTERVAL,
    CONF_MIN_CURRENT,
    CONF_PHASES,
    CONF_RESPONSE_TIMEOUT,
    CONF_TARGET_POWER,
    CONF_UPDATE_INTERVAL,
    CONF_VOLTAGE,
    DEFAULT_AVERAGE_WINDOW,
    DEFAULT_CURRENT_STEP,
    DEFAULT_DEADBAND,
    DEFAULT_EMERGENCY_POWER,
    DEFAULT_EMERGENCY_REDUCTION,
    DEFAULT_GAIN,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_STEP,
    DEFAULT_MIN_CHANGE_INTERVAL,
    DEFAULT_MIN_CURRENT,
    DEFAULT_PHASES,
    DEFAULT_RESPONSE_TIMEOUT,
    DEFAULT_TARGET_POWER,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_VOLTAGE,
    DOMAIN,
    EVENT_CONTROLLER_STARTED,
    EVENT_CONTROLLER_STOPPED,
    EVENT_CURRENT_CHANGED,
    EVENT_EMERGENCY,
    REASON_DISABLED,
    REASON_PAUSED,
    REASON_WRITE_FAILED,
)
from .controller import (
    ControlAction,
    ControlDecision,
    ControllerConfig,
    ControllerInputs,
    LoadBalanceController,
    Phases,
)

_LOGGER = logging.getLogger(__name__)


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return the effective configuration (options override data)."""
    return {**entry.data, **entry.options}


def build_controller_config(config: dict[str, Any]) -> ControllerConfig:
    """Build a validated ControllerConfig from a config entry mapping."""
    return ControllerConfig(
        target_power=float(config.get(CONF_TARGET_POWER, DEFAULT_TARGET_POWER)),
        emergency_power=float(
            config.get(CONF_EMERGENCY_POWER, DEFAULT_EMERGENCY_POWER)
        ),
        voltage=float(config.get(CONF_VOLTAGE, DEFAULT_VOLTAGE)),
        phases=Phases(config.get(CONF_PHASES, DEFAULT_PHASES)),
        min_current=float(config.get(CONF_MIN_CURRENT, DEFAULT_MIN_CURRENT)),
        max_current=float(config.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT)),
        deadband=float(config.get(CONF_DEADBAND, DEFAULT_DEADBAND)),
        max_step=float(config.get(CONF_MAX_STEP, DEFAULT_MAX_STEP)),
        gain=float(config.get(CONF_GAIN, DEFAULT_GAIN)),
        average_window=float(config.get(CONF_AVERAGE_WINDOW, DEFAULT_AVERAGE_WINDOW)),
        response_timeout=float(
            config.get(CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT)
        ),
        min_change_interval=float(
            config.get(CONF_MIN_CHANGE_INTERVAL, DEFAULT_MIN_CHANGE_INTERVAL)
        ),
        emergency_reduction=float(
            config.get(CONF_EMERGENCY_REDUCTION, DEFAULT_EMERGENCY_REDUCTION)
        ),
        current_step=float(config.get(CONF_CURRENT_STEP, DEFAULT_CURRENT_STEP)),
    )


@dataclass(slots=True)
class EVDLBData:
    """State published by the coordinator to all entities."""

    active: bool = False
    emergency: bool = False
    charging: bool = False
    error: float | None = None
    average_grid_power: float | None = None
    target_power: float = 0.0
    delta_current: float | None = None
    next_current: float | None = None
    grid_power: float | None = None
    charger_power: float | None = None
    actual_current: float | None = None
    last_execution: datetime | None = None
    last_reason: str = REASON_DISABLED
    last_change: datetime | None = None


@dataclass(slots=True)
class EVDLBRuntimeData:
    """Runtime data stored on the config entry."""

    coordinator: EVDLBCoordinator


type EVDLBConfigEntry = ConfigEntry[EVDLBRuntimeData]


class EVDLBCoordinator(DataUpdateCoordinator[EVDLBData]):
    """Periodically runs the controller and applies its decisions.

    Scheduling is handled internally by the DataUpdateCoordinator's asyncio
    based interval mechanism — no ``time_pattern`` automations involved.
    """

    config_entry: EVDLBConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EVDLBConfigEntry) -> None:
        """Initialize the coordinator from a config entry."""
        config = merged_config(entry)
        self._grid_power_entity: str = config[CONF_GRID_POWER_ENTITY]
        self._charger_power_entity: str = config[CONF_CHARGER_POWER_ENTITY]
        self._charging_status_entity: str = config[CONF_CHARGING_STATUS_ENTITY]
        self._charging_current_entity: str = config[CONF_CHARGING_CURRENT_ENTITY]

        self.controller = LoadBalanceController(build_controller_config(config))
        self._enabled = True
        self._paused = False

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=int(config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
            ),
        )

    # ------------------------------------------------------------------
    # Configuration updates
    # ------------------------------------------------------------------
    def needs_reload(self) -> bool:
        """Return True when the changed options require a full reload.

        Only changes to the selected source entities require rebuilding the
        coordinator; all tuning parameters can be applied in place.
        """
        config = merged_config(self.config_entry)
        return (
            config[CONF_GRID_POWER_ENTITY] != self._grid_power_entity
            or config[CONF_CHARGER_POWER_ENTITY] != self._charger_power_entity
            or config[CONF_CHARGING_STATUS_ENTITY] != self._charging_status_entity
            or config[CONF_CHARGING_CURRENT_ENTITY] != self._charging_current_entity
        )

    async def async_apply_options(self) -> None:
        """Apply changed tuning options without reloading the entry.

        The moving average buffer, pending command state and statistics all
        survive the update.
        """
        config = merged_config(self.config_entry)
        self.controller.update_config(build_controller_config(config))
        self.update_interval = timedelta(
            seconds=int(config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        )
        _LOGGER.debug(
            "Applied updated options in place for %s", self.config_entry.entry_id
        )
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Enable / pause API (used by the switch entity and services)
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        """Return whether the controller is enabled."""
        return self._enabled

    @property
    def paused(self) -> bool:
        """Return whether the controller is paused."""
        return self._paused

    async def async_set_enabled(
        self, enabled: bool, *, fire_event: bool = True
    ) -> None:
        """Enable or disable the controller."""
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self.controller.clear_pending()
        if fire_event:
            event = EVENT_CONTROLLER_STARTED if enabled else EVENT_CONTROLLER_STOPPED
            self.hass.bus.async_fire(event, {ATTR_ENTRY_ID: self.config_entry.entry_id})
        _LOGGER.info(
            "Controller %s: %s",
            self.config_entry.entry_id,
            "enabled" if enabled else "disabled",
        )
        await self.async_request_refresh()

    async def async_set_paused(self, paused: bool) -> None:
        """Pause or resume the controller without disabling it."""
        if self._paused == paused:
            return
        self._paused = paused
        self.controller.clear_pending()
        _LOGGER.info(
            "Controller %s: %s",
            self.config_entry.entry_id,
            "paused" if paused else "resumed",
        )
        await self.async_request_refresh()

    async def async_force_recalculate(self) -> None:
        """Run one controller cycle immediately."""
        await self.async_request_refresh()

    def reset_average(self) -> None:
        """Discard the moving average buffer."""
        self.controller.reset_average()
        _LOGGER.debug(
            "Controller %s: moving average buffer reset", self.config_entry.entry_id
        )

    # ------------------------------------------------------------------
    # State reading helpers
    # ------------------------------------------------------------------
    def _read_float(self, entity_id: str, *, is_power: bool = False) -> float | None:
        """Read a numeric entity state, returning None on invalid states.

        Power sensors reported in kW are converted to W automatically.
        """
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if is_power:
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if unit == UnitOfPower.KILO_WATT:
                value *= 1000.0
        return value

    def _read_charging(self) -> bool:
        """Return True when the charging status entity reports ON."""
        state = self.hass.states.get(self._charging_status_entity)
        return state is not None and state.state == STATE_ON

    # ------------------------------------------------------------------
    # Coordinator update
    # ------------------------------------------------------------------
    async def _async_setup(self) -> None:
        """Warn about missing source entities during initial setup."""
        for entity_id in (
            self._grid_power_entity,
            self._charger_power_entity,
            self._charging_status_entity,
            self._charging_current_entity,
        ):
            if self.hass.states.get(entity_id) is None:
                _LOGGER.warning(
                    "Configured entity %s not found (yet); the controller will "
                    "skip cycles until it becomes available",
                    entity_id,
                )

    async def _async_update_data(self) -> EVDLBData:
        """Run one full control cycle."""
        previous = self.data if self.data else EVDLBData()
        target_power = self.controller.config.target_power

        if not self._enabled or self._paused:
            idle_reason = (
                REASON_PAUSED if self._enabled and self._paused else REASON_DISABLED
            )
            return replace(
                previous,
                active=False,
                emergency=False,
                target_power=target_power,
                last_reason=idle_reason,
            )

        now_mono = time.monotonic()
        now_utc = dt_util.utcnow()

        charging = self._read_charging()
        grid_power = self._read_float(self._grid_power_entity, is_power=True)
        charger_power = self._read_float(self._charger_power_entity, is_power=True)
        actual_current = self._read_float(self._charging_current_entity)

        inputs = ControllerInputs(
            now=now_mono,
            charging=charging,
            grid_power=grid_power,
            charger_power=charger_power,
            actual_current=actual_current,
        )
        decision = self.controller.compute(inputs)

        _LOGGER.debug(
            "Cycle entry=%s charging=%s grid=%s avg=%s target=%s error=%s "
            "delta_raw=%s delta_applied=%s current=%s next=%s emergency=%s "
            "reason=%s awaiting_response=%s",
            self.config_entry.entry_id,
            charging,
            grid_power,
            decision.average_power,
            target_power,
            decision.error,
            decision.delta_raw,
            decision.delta_limited,
            actual_current,
            decision.new_current,
            decision.emergency,
            decision.reason,
            self.controller.awaiting_response,
        )

        reason: str = decision.reason.value
        last_change = previous.last_change
        next_current = (
            decision.new_current
            if decision.new_current is not None
            else previous.next_current
        )

        if decision.action is ControlAction.SET_CURRENT:
            assert decision.new_current is not None
            if await self._async_write_current(decision.new_current):
                self.controller.command_sent(
                    now_mono, decision.new_current, charger_power
                )
                last_change = now_utc
                self._fire_change_events(decision, grid_power)
            else:
                reason = REASON_WRITE_FAILED

        return EVDLBData(
            active=charging,
            emergency=decision.emergency,
            charging=charging,
            error=decision.error,
            average_grid_power=decision.average_power,
            target_power=target_power,
            delta_current=decision.delta_limited,
            next_current=next_current,
            grid_power=grid_power,
            charger_power=charger_power,
            actual_current=actual_current,
            last_execution=now_utc,
            last_reason=reason,
            last_change=last_change,
        )

    async def _async_write_current(self, value: float) -> bool:
        """Write the new charging current to the number entity."""
        try:
            await self.hass.services.async_call(
                NUMBER_DOMAIN,
                SERVICE_SET_VALUE,
                {
                    ATTR_ENTITY_ID: self._charging_current_entity,
                    ATTR_VALUE: value,
                },
                blocking=True,
            )
        except HomeAssistantError:
            _LOGGER.exception(
                "Failed to write charging current %.1f A to %s",
                value,
                self._charging_current_entity,
            )
            return False
        return True

    def _fire_change_events(
        self, decision: ControlDecision, grid_power: float | None
    ) -> None:
        """Fire the current changed (and possibly emergency) events."""
        payload = {
            ATTR_ENTRY_ID: self.config_entry.entry_id,
            ATTR_OLD_CURRENT: decision.previous_current,
            ATTR_NEW_CURRENT: decision.new_current,
            ATTR_GRID_POWER: grid_power,
            ATTR_AVERAGE_GRID_POWER: decision.average_power,
            ATTR_REASON: decision.reason.value,
            ATTR_EMERGENCY: decision.emergency,
        }
        self.hass.bus.async_fire(EVENT_CURRENT_CHANGED, payload)
        if decision.emergency:
            _LOGGER.warning(
                "Emergency: grid power %.0f W exceeded emergency threshold; "
                "reducing charging current from %s A to %s A",
                grid_power if grid_power is not None else -1.0,
                decision.previous_current,
                decision.new_current,
            )
            self.hass.bus.async_fire(EVENT_EMERGENCY, payload)
