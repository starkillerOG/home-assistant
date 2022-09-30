"""Support for Xiaomi Miio binary sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .device import XiaomiCoordinatedMiioEntity

_LOGGER = logging.getLogger(__name__)


@dataclass
class XiaomiBinarySensorDescription(BinarySensorEntityDescription):
    """A class that describes binary sensor entities."""

    value: Callable | None = None
    parent_key: str | None = None


class XiaomiBinarySensor(XiaomiCoordinatedMiioEntity, BinarySensorEntity):
    """Representation of a Xiaomi Humidifier binary sensor."""

    _attr_has_entity_name = True
    entity_description: XiaomiBinarySensorDescription

    def __init__(self, device, sensor, entry, coordinator):
        """Initialize the entity."""
        self._name = sensor.name
        self._property = sensor.property
        unique_id = f"{entry.unique_id}_binarysensor_{sensor.id}"

        super().__init__(device, entry, unique_id, coordinator)

        entity_category = None
        if "entity_category" in sensor.extras:
            entity_category = EntityCategory(sensor.extras.get("entity_category"))

        description = XiaomiBinarySensorDescription(
            key=sensor.id,
            name=sensor.name,
            icon=sensor.extras.get("icon"),
            device_class=sensor.extras.get("device_class"),
            entity_category=entity_category,
        )

        self.entity_description = description

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_is_on = bool(getattr(self.coordinator.data, self._property))
        _LOGGER.debug("Got update: %s", self)

        super()._handle_coordinator_update()
