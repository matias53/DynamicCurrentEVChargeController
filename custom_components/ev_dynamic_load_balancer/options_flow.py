"""Options flow and shared form schemas for the EV Dynamic Load Balancer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
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
    UPDATE_INTERVAL_OPTIONS,
)

# ---------------------------------------------------------------------------
# Schema builders (shared between the config flow and the options flow)
# ---------------------------------------------------------------------------


def build_entities_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the entity selection form schema."""

    def _required(key: str) -> vol.Required:
        if key in defaults:
            return vol.Required(key, default=defaults[key])
        return vol.Required(key)

    return vol.Schema(
        {
            _required(CONF_GRID_POWER_ENTITY): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            _required(CONF_CHARGER_POWER_ENTITY): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            _required(CONF_CHARGING_STATUS_ENTITY): EntitySelector(
                EntitySelectorConfig(
                    domain=["binary_sensor", "input_boolean", "switch"]
                )
            ),
            _required(CONF_CHARGING_CURRENT_ENTITY): EntitySelector(
                EntitySelectorConfig(domain=["number", "input_number"])
            ),
        }
    )


def build_electrical_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the electrical parameters form schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TARGET_POWER,
                default=defaults.get(CONF_TARGET_POWER, DEFAULT_TARGET_POWER),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=100_000,
                    step=100,
                    unit_of_measurement=UnitOfPower.WATT,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_EMERGENCY_POWER,
                default=defaults.get(CONF_EMERGENCY_POWER, DEFAULT_EMERGENCY_POWER),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=500,
                    max=150_000,
                    step=100,
                    unit_of_measurement=UnitOfPower.WATT,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_VOLTAGE,
                default=defaults.get(CONF_VOLTAGE, DEFAULT_VOLTAGE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=100,
                    max=440,
                    step=1,
                    unit_of_measurement=UnitOfElectricPotential.VOLT,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_PHASES,
                default=defaults.get(CONF_PHASES, DEFAULT_PHASES),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=["single", "three"],
                    translation_key="phases",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_MIN_CURRENT,
                default=defaults.get(CONF_MIN_CURRENT, DEFAULT_MIN_CURRENT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=63,
                    step=1,
                    unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MAX_CURRENT,
                default=defaults.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=63,
                    step=1,
                    unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


def build_control_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the controller parameters form schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=str(
                    defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[str(seconds) for seconds in UPDATE_INTERVAL_OPTIONS],
                    translation_key="update_interval",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_DEADBAND,
                default=defaults.get(CONF_DEADBAND, DEFAULT_DEADBAND),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=5000,
                    step=50,
                    unit_of_measurement=UnitOfPower.WATT,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MAX_STEP,
                default=defaults.get(CONF_MAX_STEP, DEFAULT_MAX_STEP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.5,
                    max=16,
                    step=0.5,
                    unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_GAIN,
                default=defaults.get(CONF_GAIN, DEFAULT_GAIN),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1,
                    max=2.0,
                    step=0.05,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_AVERAGE_WINDOW,
                default=defaults.get(CONF_AVERAGE_WINDOW, DEFAULT_AVERAGE_WINDOW),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=5,
                    max=600,
                    step=5,
                    unit_of_measurement=UnitOfTime.SECONDS,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_RESPONSE_TIMEOUT,
                default=defaults.get(CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=120,
                    step=1,
                    unit_of_measurement=UnitOfTime.SECONDS,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MIN_CHANGE_INTERVAL,
                default=defaults.get(
                    CONF_MIN_CHANGE_INTERVAL, DEFAULT_MIN_CHANGE_INTERVAL
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=300,
                    step=1,
                    unit_of_measurement=UnitOfTime.SECONDS,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_EMERGENCY_REDUCTION,
                default=defaults.get(
                    CONF_EMERGENCY_REDUCTION, DEFAULT_EMERGENCY_REDUCTION
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=32,
                    step=1,
                    unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_CURRENT_STEP,
                default=defaults.get(CONF_CURRENT_STEP, DEFAULT_CURRENT_STEP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1,
                    max=5,
                    step=0.1,
                    unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


def validate_electrical(data: Mapping[str, Any]) -> dict[str, str]:
    """Cross-field validation for the electrical step."""
    errors: dict[str, str] = {}
    if data[CONF_EMERGENCY_POWER] <= data[CONF_TARGET_POWER]:
        errors[CONF_EMERGENCY_POWER] = "emergency_below_target"
    if data[CONF_MAX_CURRENT] <= data[CONF_MIN_CURRENT]:
        errors[CONF_MAX_CURRENT] = "max_below_min"
    return errors


def normalize_control(data: dict[str, Any]) -> dict[str, Any]:
    """Convert form values to their storage types."""
    data[CONF_UPDATE_INTERVAL] = int(data[CONF_UPDATE_INTERVAL])
    return data


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class EVDLBOptionsFlowHandler(OptionsFlow):
    """Handle reconfiguration of an existing entry from the UI."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._options: dict[str, Any] = {}

    def _defaults(self) -> dict[str, Any]:
        """Return the current effective configuration."""
        return {
            **self.config_entry.data,
            **self.config_entry.options,
            **self._options,
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle entity selection."""
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_electrical()
        return self.async_show_form(
            step_id="init",
            data_schema=build_entities_schema(self._defaults()),
        )

    async def async_step_electrical(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle electrical parameters."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_electrical(user_input)
            if not errors:
                self._options.update(user_input)
                return await self.async_step_control()
        return self.async_show_form(
            step_id="electrical",
            data_schema=build_electrical_schema(self._defaults()),
            errors=errors,
        )

    async def async_step_control(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle controller parameters and store the options."""
        if user_input is not None:
            self._options.update(normalize_control(user_input))
            return self.async_create_entry(data=self._options)
        return self.async_show_form(
            step_id="control",
            data_schema=build_control_schema(self._defaults()),
        )
