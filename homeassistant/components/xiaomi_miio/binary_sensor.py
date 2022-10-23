"""Support for Xiaomi Miio binary sensors."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE,
    CONF_FLOW_TYPE,
    DOMAIN,
    KEY_COORDINATOR,
    KEY_DEVICE,
    MODEL_AIRFRESH_A1,
    MODEL_AIRFRESH_T2017,
    MODEL_FAN_ZA5,
    MODELS_HUMIDIFIER_MIIO,
    MODELS_HUMIDIFIER_MIOT,
    MODELS_HUMIDIFIER_MJJSQ,
)
from .device import XiaomiCoordinatedMiioEntity
from .ng_binary_sensor import XiaomiBinarySensor

_LOGGER = logging.getLogger(__name__)

ATTR_NO_WATER = "no_water"
ATTR_PTC_STATUS = "ptc_status"
ATTR_POWERSUPPLY_ATTACHED = "powersupply_attached"
ATTR_WATER_TANK_DETACHED = "water_tank_detached"
ATTR_MOP_ATTACHED = "is_water_box_carriage_attached"
ATTR_WATER_BOX_ATTACHED = "is_water_box_attached"
ATTR_WATER_SHORTAGE = "is_water_shortage"


@dataclass
class XiaomiMiioBinarySensorDescription(BinarySensorEntityDescription):
    """A class that describes binary sensor entities."""

    value: Callable | None = None
    parent_key: str | None = None


BINARY_SENSOR_TYPES = (
    XiaomiMiioBinarySensorDescription(
        key=ATTR_NO_WATER,
        name="Water tank empty",
        icon="mdi:water-off-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    XiaomiMiioBinarySensorDescription(
        key=ATTR_WATER_TANK_DETACHED,
        name="Water tank",
        icon="mdi:car-coolant-level",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value=lambda value: not value,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    XiaomiMiioBinarySensorDescription(
        key=ATTR_PTC_STATUS,
        name="Auxiliary heat status",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    XiaomiMiioBinarySensorDescription(
        key=ATTR_POWERSUPPLY_ATTACHED,
        name="Power supply",
        device_class=BinarySensorDeviceClass.PLUG,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

AIRFRESH_A1_BINARY_SENSORS = (ATTR_PTC_STATUS,)
FAN_ZA5_BINARY_SENSORS = (ATTR_POWERSUPPLY_ATTACHED,)

HUMIDIFIER_MIIO_BINARY_SENSORS = (ATTR_WATER_TANK_DETACHED,)
HUMIDIFIER_MIOT_BINARY_SENSORS = (ATTR_WATER_TANK_DETACHED,)
HUMIDIFIER_MJJSQ_BINARY_SENSORS = (ATTR_NO_WATER, ATTR_WATER_TANK_DETACHED)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Xiaomi sensor from a config entry."""
    entities: list[XiaomiGenericBinarySensor | XiaomiBinarySensor] = []

    if config_entry.data[CONF_FLOW_TYPE] == CONF_DEVICE:
        model = config_entry.data[CONF_MODEL]
        sensors: Iterable[str] = []
        if model in MODEL_AIRFRESH_A1 or model in MODEL_AIRFRESH_T2017:
            sensors = AIRFRESH_A1_BINARY_SENSORS
        elif model in MODEL_FAN_ZA5:
            sensors = FAN_ZA5_BINARY_SENSORS
        elif model in MODELS_HUMIDIFIER_MIIO:
            sensors = HUMIDIFIER_MIIO_BINARY_SENSORS
        elif model in MODELS_HUMIDIFIER_MIOT:
            sensors = HUMIDIFIER_MIOT_BINARY_SENSORS
        elif model in MODELS_HUMIDIFIER_MJJSQ:
            sensors = HUMIDIFIER_MJJSQ_BINARY_SENSORS

        for description in BINARY_SENSOR_TYPES:
            if description.key not in sensors:
                continue
            entities.append(
                XiaomiGenericBinarySensor(
                    hass.data[DOMAIN][config_entry.entry_id][KEY_DEVICE],
                    config_entry,
                    f"{description.key}_{config_entry.unique_id}",
                    hass.data[DOMAIN][config_entry.entry_id][KEY_COORDINATOR],
                    description,
                )
            )

        device = hass.data[DOMAIN][config_entry.entry_id].get(KEY_DEVICE)
        coordinator = hass.data[DOMAIN][config_entry.entry_id][KEY_COORDINATOR]
        for sensor in device.sensors().values():
            if sensor.type == "binary":
                if getattr(coordinator.data, sensor.property) is None:
                    _LOGGER.debug("Skipping %s as it's value was None", sensor.property)
                    continue

                entities.append(
                    XiaomiBinarySensor(device, sensor, config_entry, coordinator)
                )

    async_add_entities(entities)


class XiaomiGenericBinarySensor(XiaomiCoordinatedMiioEntity, BinarySensorEntity):
    """Representation of a Xiaomi Humidifier binary sensor."""

    entity_description: XiaomiMiioBinarySensorDescription

    def __init__(self, device, entry, unique_id, coordinator, description):
        """Initialize the entity."""
        super().__init__(device, entry, unique_id, coordinator)

        self.entity_description = description
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )
        self._attr_is_on = self._determine_native_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_is_on = self._determine_native_value()

        super()._handle_coordinator_update()

    def _determine_native_value(self):
        """Determine native value."""
        if self.entity_description.parent_key is not None:
            return self._extract_value_from_attribute(
                getattr(self.coordinator.data, self.entity_description.parent_key),
                self.entity_description.key,
            )

        state = self._extract_value_from_attribute(
            self.coordinator.data, self.entity_description.key
        )
        if self.entity_description.value is not None and state is not None:
            return self.entity_description.value(state)

        return state
