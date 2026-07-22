"""Config flow for the EV Dynamic Load Balancer integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.core import callback

from .const import CONF_CHARGING_CURRENT_ENTITY, DOMAIN
from .options_flow import (
    EVDLBOptionsFlowHandler,
    build_control_schema,
    build_electrical_schema,
    build_entities_schema,
    normalize_control,
    validate_electrical,
)


class EVDLBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial UI configuration."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EVDLBOptionsFlowHandler:
        """Return the options flow handler."""
        return EVDLBOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle entity selection."""
        if user_input is not None:
            # One controller instance per charging current entity.
            await self.async_set_unique_id(user_input[CONF_CHARGING_CURRENT_ENTITY])
            self._abort_if_unique_id_configured()
            self._data.update(user_input)
            return await self.async_step_electrical()
        return self.async_show_form(
            step_id="user",
            data_schema=build_entities_schema(self._data),
        )

    async def async_step_electrical(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle electrical parameters."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_electrical(user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_control()
        return self.async_show_form(
            step_id="electrical",
            data_schema=build_electrical_schema(self._data),
            errors=errors,
        )

    async def async_step_control(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle controller parameters and create the entry."""
        if user_input is not None:
            self._data.update(normalize_control(user_input))
            return self.async_create_entry(
                title="EV Dynamic Load Balancer",
                data=self._data,
            )
        return self.async_show_form(
            step_id="control",
            data_schema=build_control_schema(self._data),
        )
