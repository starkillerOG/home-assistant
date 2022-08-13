from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.xiaomi_miio.device import XiaomiCoordinatedMiioEntity
from homeassistant.core import callback

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
        self._name = name = sensor.name
        self._property = sensor.property
        from homeassistant.util import slugify

        unique_id = f"{entry.unique_id}_binarysensor_{slugify(name)}"

        super().__init__(device, entry, unique_id, coordinator)

        description = XiaomiBinarySensorDescription(
            key=sensor.id,
            name=sensor.name,
            icon=sensor.extras.get("icon"),
            device_class=sensor.extras.get("device_class"),
            entity_category=sensor.extras.get("entity_category"),
        )

        self.entity_description = description

    @callback
    def _handle_coordinator_update(self) -> None:
        try:
            self._attr_is_on = bool(getattr(self.coordinator.data, self._property))
        except AttributeError as ex:
            # TODO: ugly fallback to custom vacuum container
            self._attr_is_on = bool(
                getattr(self.coordinator.data.status, self._property)
            )

        self._attr_available = (
            self._attr_is_on is not None
        )  # this is necessary to get the values displayed
        _LOGGER.error("Got an update for %s", self)

        super()._handle_coordinator_update()
