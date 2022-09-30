"""Support for Xiaomi Miio select entities."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .device import XiaomiCoordinatedMiioEntity

_LOGGER = logging.getLogger(__name__)


class XiaomiSelect(XiaomiCoordinatedMiioEntity, SelectEntity):
    """Representation of a generic Xiaomi attribute selector."""

    _attr_has_entity_name = True

    def __init__(self, device, setting, entry, coordinator):
        """Initialize the generic Xiaomi attribute selector."""
        self._name = setting.name
        unique_id = f"{entry.unique_id}_select_{setting.id}"
        self._setter = setting.setter

        super().__init__(device, entry, unique_id, coordinator)
        self._choices = setting.choices
        self._attr_current_option = None  # TODO we don't know the value, but the parent wants it? # pylint: disable=fixme

        entity_category = None
        if "entity_category" in setting.extras:
            entity_category = EntityCategory(setting.extras.get("entity_category"))

        self.entity_description = SelectEntityDescription(
            key=setting.id,
            name=setting.name,
            icon=setting.extras.get("icon"),
            device_class=setting.extras.get("device_class"),
            entity_category=entity_category,
            # entity_category=EntityCategory.CONFIG,
        )
        self._attr_options = [x.name for x in self._choices]

    @callback
    def _handle_coordinator_update(self):
        """Fetch state from the device."""
        value = self._extract_value_from_attribute(
            self.coordinator.data, self.entity_description.key
        )
        # Sometimes (quite rarely) the device returns None as the LED brightness so we
        # check that the value is not None before updating the state.
        if value is not None:
            try:
                self._attr_current_option = self._choices(value).name
            except ValueError:
                self._attr_current_option = "Unknown"
            finally:
                _LOGGER.debug("Got update: %s", self)
                self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Set an option of the miio device."""
        _LOGGER.debug("Setting select value to: %s", option)
        if await self._try_command(
            "Setting the select value failed",
            self._setter,
            self._choices[option],
        ):
            self._attr_current_option = option
            self.async_write_ha_state()
