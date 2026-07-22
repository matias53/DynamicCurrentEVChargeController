"""Shared entity base class for the EV Dynamic Load Balancer."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENTITY_ID_PREFIX, MANUFACTURER, MODEL
from .coordinator import EVDLBCoordinator


class EVDLBEntity(CoordinatorEntity[EVDLBCoordinator]):
    """Base entity tied to the coordinator and the integration device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EVDLBCoordinator, key: str, platform: str) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        # Suggest predictable entity ids (e.g. sensor.evdlb_error).  If the id
        # is taken (multiple config entries) Home Assistant adds a suffix.
        self.entity_id = f"{platform}.{ENTITY_ID_PREFIX}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
