"""Support for Xiaomi Miio sensor entities."""
from __future__ import annotations
import datetime
from enum import Enum

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .device import XiaomiCoordinatedMiioEntity
from .sensor import XiaomiMiioSensorDescription

from homeassistant.util import dt as dt_util


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

        entity_category = None
        if "entity_category" in sensor.extras:
            entity_category = EntityCategory(sensor.extras.get("entity_category"))

        description = XiaomiMiioSensorDescription(
            key=sensor.id,
            name=sensor.name,
            native_unit_of_measurement=sensor.unit,
            icon=sensor.extras.get("icon"),
            device_class=sensor.extras.get("device_class"),
            state_class=sensor.extras.get("state_class"),
            entity_category=entity_category,
            entity_registry_enabled_default=sensor.extras.get("enabled_default", True),
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
        native_value = getattr(self.coordinator.data, self._property)
        # TODO: add type handling # pylint: disable=fixme
        # if self.entity_description.parent_key is not None:
        #     native_value = self._extract_value_from_attribute(
        #         getattr(self.coordinator.data, self.entity_description.parent_key),
        #         self.entity_description.key,
        #     )
        # else:
        #     native_value = self._extract_value_from_attribute(
        #         self.coordinator.data, self.entity_description.key
        #     )

        if (
            self.device_class == SensorDeviceClass.TIMESTAMP
            and native_value is not None
            and (native_datetime := dt_util.parse_datetime(str(native_value)))
            is not None
        ):
            return native_datetime.astimezone(dt_util.UTC)
        if isinstance(native_value, Enum):
            return native_value.value
        if isinstance(native_value, datetime.timedelta):
            return self._parse_time_delta(native_value)
        if isinstance(native_value, datetime.time):
            return self._parse_datetime_time(native_value)
        if isinstance(native_value, datetime.datetime):
            return self._parse_datetime_datetime(native_value)

        return native_value
