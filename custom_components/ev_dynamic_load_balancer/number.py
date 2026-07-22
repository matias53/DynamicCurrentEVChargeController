"""Number entities exposing the controller tuning parameters.

Each number writes its value back to the config entry options.  The update
listener applies tuning changes in place (no reload), so parameters can be
adjusted on the fly — from the UI, automations or scripts — while the
controller keeps running.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    Platform,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_AVERAGE_WINDOW,
    CONF_DEADBAND,
    CONF_EMERGENCY_POWER,
    CONF_EMERGENCY_REDUCTION,
    CONF_GAIN,
    CONF_MAX_CURRENT,
    CONF_MAX_STEP,
    CONF_MIN_CHANGE_INTERVAL,
    CONF_MIN_CURRENT,
    CONF_RESPONSE_TIMEOUT,
    CONF_TARGET_POWER,
    DEFAULT_AVERAGE_WINDOW,
    DEFAULT_DEADBAND,
    DEFAULT_EMERGENCY_POWER,
    DEFAULT_EMERGENCY_REDUCTION,
    DEFAULT_GAIN,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_STEP,
    DEFAULT_MIN_CHANGE_INTERVAL,
    DEFAULT_MIN_CURRENT,
    DEFAULT_RESPONSE_TIMEOUT,
    DEFAULT_TARGET_POWER,
    DOMAIN,
)
from .coordinator import (
    EVDLBConfigEntry,
    EVDLBCoordinator,
    build_controller_config,
    merged_config,
)
from .entity import EVDLBEntity


@dataclass(frozen=True, kw_only=True)
class EVDLBNumberEntityDescription(NumberEntityDescription):
    """Describes a tunable controller parameter.

    The ``key`` doubles as the config entry option key.
    """

    default: float


NUMBERS: tuple[EVDLBNumberEntityDescription, ...] = (
    EVDLBNumberEntityDescription(
        key=CONF_TARGET_POWER,
        translation_key="target_power_setting",
        default=DEFAULT_TARGET_POWER,
        native_min_value=0,
        native_max_value=100_000,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_EMERGENCY_POWER,
        translation_key="emergency_power_setting",
        default=DEFAULT_EMERGENCY_POWER,
        native_min_value=500,
        native_max_value=150_000,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_MIN_CURRENT,
        translation_key="min_current_setting",
        default=DEFAULT_MIN_CURRENT,
        native_min_value=0,
        native_max_value=63,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_MAX_CURRENT,
        translation_key="max_current_setting",
        default=DEFAULT_MAX_CURRENT,
        native_min_value=1,
        native_max_value=63,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_DEADBAND,
        translation_key="deadband_setting",
        default=DEFAULT_DEADBAND,
        native_min_value=0,
        native_max_value=5000,
        native_step=50,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_MAX_STEP,
        translation_key="max_step_setting",
        default=DEFAULT_MAX_STEP,
        native_min_value=0.5,
        native_max_value=16,
        native_step=0.5,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_GAIN,
        translation_key="gain_setting",
        default=DEFAULT_GAIN,
        native_min_value=0.1,
        native_max_value=2.0,
        native_step=0.05,
        mode=NumberMode.SLIDER,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_AVERAGE_WINDOW,
        translation_key="average_window_setting",
        default=DEFAULT_AVERAGE_WINDOW,
        native_min_value=5,
        native_max_value=600,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_RESPONSE_TIMEOUT,
        translation_key="response_timeout_setting",
        default=DEFAULT_RESPONSE_TIMEOUT,
        native_min_value=0,
        native_max_value=120,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_MIN_CHANGE_INTERVAL,
        translation_key="min_change_interval_setting",
        default=DEFAULT_MIN_CHANGE_INTERVAL,
        native_min_value=0,
        native_max_value=300,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberMode.BOX,
    ),
    EVDLBNumberEntityDescription(
        key=CONF_EMERGENCY_REDUCTION,
        translation_key="emergency_reduction_setting",
        default=DEFAULT_EMERGENCY_REDUCTION,
        native_min_value=1,
        native_max_value=32,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EVDLBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the tuning number entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(EVDLBNumber(coordinator, description) for description in NUMBERS)


class EVDLBNumber(EVDLBEntity, NumberEntity):
    """A tunable controller parameter backed by the config entry options."""

    entity_description: EVDLBNumberEntityDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: EVDLBCoordinator,
        description: EVDLBNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, description.key, Platform.NUMBER)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        """Return the currently configured value."""
        value = merged_config(self.coordinator.config_entry).get(
            self.entity_description.key, self.entity_description.default
        )
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Validate and store a new value in the config entry options."""
        entry = self.coordinator.config_entry
        new_options = {**entry.options, self.entity_description.key: value}
        candidate = {**entry.data, **new_options}
        try:
            build_controller_config(candidate)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_tuning",
                translation_placeholders={"error": str(err)},
            ) from err
        # Persist the value; the entry update listener applies it in place.
        self.hass.config_entries.async_update_entry(entry, options=new_options)
        self.async_write_ha_state()
