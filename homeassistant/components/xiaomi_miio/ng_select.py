from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.components.xiaomi_miio.device import XiaomiCoordinatedMiioEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)


class XiaomiSelect(XiaomiCoordinatedMiioEntity, SelectEntity):
    """Representation of a generic Xiaomi attribute selector."""

    _attr_has_entity_name = True

    def __init__(self, device, setting, entry, coordinator):
        """Initialize the generic Xiaomi attribute selector."""
        self._name = name = setting.name
        unique_id = f"{entry.unique_id}_{slugify(name)}"
        self._setter = setting.setter

        super().__init__(device, entry, unique_id, coordinator)
        self._choices = setting.choices
        self._attr_current_option = (
            None  # TODO we don't know the value, but the parent wants it?
        )

        self.entity_description = SelectEntityDescription(
            key=setting.id,
            name=setting.name,
            icon=setting.icon,
            # device_class="xiaomi_miio__led_brightness",
            entity_category=EntityCategory.CONFIG,
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
            except:
                pass
            finally:
                _LOGGER.error("New select value: %s", self._attr_current_option)
                self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Set an option of the miio device."""
        if await self._try_command(
            "Setting the led brightness of the miio device failed.",
            self._setter,
            self._choices[option].value,
        ):
            self._attr_current_option = option
            self.async_write_ha_state()
