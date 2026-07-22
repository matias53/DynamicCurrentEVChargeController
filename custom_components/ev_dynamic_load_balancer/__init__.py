"""The EV Dynamic Load Balancer integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ENTRY_ID,
    DOMAIN,
    EVENT_CONTROLLER_STARTED,
    EVENT_CONTROLLER_STOPPED,
)
from .coordinator import EVDLBConfigEntry, EVDLBCoordinator, EVDLBRuntimeData
from .services import async_setup_services

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (register domain services)."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EVDLBConfigEntry) -> bool:
    """Set up EV Dynamic Load Balancer from a config entry."""
    coordinator = EVDLBCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = EVDLBRuntimeData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    hass.bus.async_fire(EVENT_CONTROLLER_STARTED, {ATTR_ENTRY_ID: entry.entry_id})
    return True


async def _async_update_listener(hass: HomeAssistant, entry: EVDLBConfigEntry) -> None:
    """Handle options updates.

    A full reload is only needed when the selected source entities changed;
    tuning parameters are applied in place so the controller state (moving
    average buffer, statistics) survives adjustments.
    """
    coordinator = entry.runtime_data.coordinator
    if coordinator.needs_reload():
        await hass.config_entries.async_reload(entry.entry_id)
    else:
        await coordinator.async_apply_options()


async def async_unload_entry(hass: HomeAssistant, entry: EVDLBConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data.coordinator.enabled:
        hass.bus.async_fire(EVENT_CONTROLLER_STOPPED, {ATTR_ENTRY_ID: entry.entry_id})
    return unload_ok
