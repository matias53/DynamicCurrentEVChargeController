"""Diagnostic sensors for the EV Dynamic Load Balancer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    Platform,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import REASON_DISABLED, REASON_PAUSED, REASON_WRITE_FAILED
from .controller import Reason
from .coordinator import EVDLBConfigEntry, EVDLBCoordinator, EVDLBData
from .entity import EVDLBEntity

REASON_OPTIONS: list[str] = [
    *[reason.value for reason in Reason],
    REASON_DISABLED,
    REASON_PAUSED,
    REASON_WRITE_FAILED,
]


@dataclass(frozen=True, kw_only=True)
class EVDLBSensorEntityDescription(SensorEntityDescription):
    """Describes an EV Dynamic Load Balancer sensor."""

    value_fn: Callable[[EVDLBData], StateType | datetime]


SENSORS: tuple[EVDLBSensorEntityDescription, ...] = (
    EVDLBSensorEntityDescription(
        key="error",
        translation_key="error",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.error,
    ),
    EVDLBSensorEntityDescription(
        key="average_grid_power",
        translation_key="average_grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: data.average_grid_power,
    ),
    EVDLBSensorEntityDescription(
        key="target_power",
        translation_key="target_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.target_power,
    ),
    EVDLBSensorEntityDescription(
        key="delta_current",
        translation_key="delta_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.delta_current,
    ),
    EVDLBSensorEntityDescription(
        key="next_current",
        translation_key="next_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.next_current,
    ),
    EVDLBSensorEntityDescription(
        key="last_execution",
        translation_key="last_execution",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_execution,
    ),
    EVDLBSensorEntityDescription(
        key="last_reason",
        translation_key="last_reason",
        device_class=SensorDeviceClass.ENUM,
        options=REASON_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_reason,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EVDLBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the diagnostic sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(EVDLBSensor(coordinator, description) for description in SENSORS)


class EVDLBSensor(EVDLBEntity, SensorEntity):
    """A diagnostic sensor driven by the coordinator."""

    entity_description: EVDLBSensorEntityDescription

    def __init__(
        self,
        coordinator: EVDLBCoordinator,
        description: EVDLBSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key, Platform.SENSOR)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator.data)
