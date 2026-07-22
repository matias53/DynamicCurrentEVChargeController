"""Domain services for the EV Dynamic Load Balancer."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
import voluptuous as vol

from .const import (
    ATTR_ENTRY_ID,
    DOMAIN,
    SERVICE_DISABLE,
    SERVICE_ENABLE,
    SERVICE_FORCE_RECALCULATE,
    SERVICE_PAUSE,
    SERVICE_RESET_AVERAGE,
    SERVICE_RESUME,
)
from .coordinator import EVDLBCoordinator

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})


def _coordinators_for_call(
    hass: HomeAssistant, call: ServiceCall
) -> list[EVDLBCoordinator]:
    """Resolve the coordinators targeted by a service call."""
    entry_id: str | None = call.data.get(ATTR_ENTRY_ID)
    if entry_id is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_entry_id",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entry_id": entry_id},
            )
        return [entry.runtime_data.coordinator]

    coordinators = [
        entry.runtime_data.coordinator
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not coordinators:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_entries_loaded",
        )
    return coordinators


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all domain services."""

    async def _enable(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_set_enabled(True)

    async def _disable(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_set_enabled(False)

    async def _pause(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_set_paused(True)

    async def _resume(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_set_paused(False)

    async def _force_recalculate(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_force_recalculate()

    async def _reset_average(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            coordinator.reset_average()

    for service, handler in (
        (SERVICE_ENABLE, _enable),
        (SERVICE_DISABLE, _disable),
        (SERVICE_PAUSE, _pause),
        (SERVICE_RESUME, _resume),
        (SERVICE_FORCE_RECALCULATE, _force_recalculate),
        (SERVICE_RESET_AVERAGE, _reset_average),
    ):
        hass.services.async_register(DOMAIN, service, handler, schema=SERVICE_SCHEMA)
