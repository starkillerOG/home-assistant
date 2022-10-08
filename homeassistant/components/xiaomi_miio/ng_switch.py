"""Support for Xiaomi Miio switch entities."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .device import XiaomiCoordinatedMiioEntity

_LOGGER = logging.getLogger(__name__)


class XiaomiSwitch(XiaomiCoordinatedMiioEntity, SwitchEntity):
    """Representation of a Xiaomi Plug Generic."""

    entity_description: SwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(self, device, switch, entry, coordinator):
        """Initialize the plug switch."""
        self._name = name = switch.name
        self._property = switch.property
        self._setter = switch.setter
        unique_id = f"{entry.unique_id}_switch_{switch.id}"

        super().__init__(device, entry, unique_id, coordinator)

        entity_category = None
        if "entity_category" in switch.extras:
            entity_category = EntityCategory(switch.extras.get("entity_category"))

        description = SwitchEntityDescription(
            key=switch.property,
            name=name,
            icon=switch.extras.get("icon"),
            device_class=switch.extras.get("device_class"),
            entity_category=entity_category,
        )

        _LOGGER.debug("Adding switch: %s", description)

        self._attr_is_on = self._extract_value_from_attribute(
            self.coordinator.data, description.key
        )
        self.entity_description = description

    @callback
    def _handle_coordinator_update(self):
        """Fetch state from the device."""
        # On state change the device doesn't provide the new state immediately.
        self._attr_is_on = self._extract_value_from_attribute(
            self.coordinator.data, self.entity_description.key
        )
        _LOGGER.debug("Got update: %s", self)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on an option of the miio device."""
        if await self._try_command("Turning %s on failed", self._setter, True):
            # Write state back to avoid switch flips with a slow response
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off an option of the miio device."""
        if await self._try_command("Turning off failed", self._setter, False):
            # Write state back to avoid switch flips with a slow response
            self._attr_is_on = False
            self.async_write_ha_state()
