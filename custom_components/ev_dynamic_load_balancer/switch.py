"""Enable/disable switch for the EV Dynamic Load Balancer."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import EVDLBConfigEntry, EVDLBCoordinator
from .entity import EVDLBEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EVDLBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the enabled switch."""
    async_add_entities([EVDLBEnabledSwitch(entry.runtime_data.coordinator)])


class EVDLBEnabledSwitch(EVDLBEntity, SwitchEntity, RestoreEntity):
    """Switch that enables or disables the load balancing controller."""

    _attr_translation_key = "enabled"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EVDLBCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "enabled", Platform.SWITCH)

    async def async_added_to_hass(self) -> None:
        """Restore the previous enabled state across restarts."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None and (
            last_state.state == STATE_OFF
        ):
            await self.coordinator.async_set_enabled(False)

    @property
    def is_on(self) -> bool:
        """Return True when the controller is enabled."""
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the controller."""
        await self.coordinator.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the controller."""
        await self.coordinator.async_set_enabled(False)
        self.async_write_ha_state()
