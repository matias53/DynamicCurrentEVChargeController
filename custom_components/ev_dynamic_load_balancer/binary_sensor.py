"""Binary sensors for the EV Dynamic Load Balancer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EVDLBConfigEntry, EVDLBCoordinator, EVDLBData
from .entity import EVDLBEntity


@dataclass(frozen=True, kw_only=True)
class EVDLBBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an EV Dynamic Load Balancer binary sensor."""

    value_fn: Callable[[EVDLBCoordinator, EVDLBData], bool]


BINARY_SENSORS: tuple[EVDLBBinarySensorEntityDescription, ...] = (
    EVDLBBinarySensorEntityDescription(
        key="controller_active",
        translation_key="controller_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda coordinator, data: (
            coordinator.enabled and not coordinator.paused and data.charging
        ),
    ),
    EVDLBBinarySensorEntityDescription(
        key="emergency",
        translation_key="emergency",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda coordinator, data: data.emergency,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EVDLBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EVDLBBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class EVDLBBinarySensor(EVDLBEntity, BinarySensorEntity):
    """A binary sensor driven by the coordinator."""

    entity_description: EVDLBBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EVDLBCoordinator,
        description: EVDLBBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key, Platform.BINARY_SENSOR)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return True when the condition is met."""
        return self.entity_description.value_fn(self.coordinator, self.coordinator.data)
