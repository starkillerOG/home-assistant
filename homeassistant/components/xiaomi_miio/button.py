"""Support for Xiaomi buttons."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_COORDINATOR, KEY_DEVICE
from .ng_button import XiaomiButton

ATTR_RESET_DUST_FILTER = "reset_dust_filter"
ATTR_RESET_UPPER_FILTER = "reset_upper_filter"


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button from a config entry."""
    entities = []
    device = hass.data[DOMAIN][config_entry.entry_id][KEY_DEVICE]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][KEY_COORDINATOR]

    for button in device.buttons():
        entities.append(XiaomiButton(button, device, config_entry, coordinator))

    async_add_entities(entities)
