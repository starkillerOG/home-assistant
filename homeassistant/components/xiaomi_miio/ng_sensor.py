"""Support for Xiaomi Miio sensor entities."""
from __future__ import annotations

from enum import Enum
import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.xiaomi_miio.device import XiaomiCoordinatedMiioEntity
from homeassistant.components.xiaomi_miio.sensor import XiaomiMiioSensorDescription
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)


class XiaomiSensor(XiaomiCoordinatedMiioEntity, SensorEntity):
    """Representation of a Xiaomi generic sensor."""

    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        device,
        sensor,
        entry,
        coordinator,
    ):
        """Initialize the entity."""
        self._name = sensor.name
        self._property = sensor.property

        unique_id = f"{entry.unique_id}_sensor_{sensor.id}"

        description = XiaomiMiioSensorDescription(
            key=sensor.id,
            name=sensor.name,
            native_unit_of_measurement=sensor.unit,
            icon=sensor.extras.get("icon"),
            device_class=sensor.extras.get("device_class"),
            state_class=sensor.extras.get("state_class"),
            entity_category=sensor.extras.get("entity_category"),
        )
        _LOGGER.debug("Adding sensor: %s", description)
        super().__init__(device, entry, unique_id, coordinator)
        self.entity_description = description
        self._attr_native_value = self._determine_native_value()

    @callback
    def _handle_coordinator_update(self):
        """Fetch state from the device."""
        native_value = self._determine_native_value()
        # Sometimes (quite rarely) the device returns None as the sensor value so we
        # check that the value is not None before updating the state.
        _LOGGER.debug("Got update: %s", self)
        if native_value is not None:
            self._attr_native_value = native_value
            self._attr_available = True
            self.async_write_ha_state()

    def _determine_native_value(self):
        """Determine native value."""
        val = getattr(self.coordinator.data, self._property)

        if isinstance(val, Enum):
            val = val.name

        # TODO: check how to handle timestamps properly
        # if(self.device_class == SensorDeviceClass.TIMESTAMP): ...
        #     native_dt = dt_util.parse_datetime(val)
        #      return native_dt.astimezone(dt_util.UTC)

        return val
