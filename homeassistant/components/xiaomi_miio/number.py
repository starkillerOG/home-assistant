"""Motor speed support for Xiaomi Mi Air Humidifier."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEVICE, CONF_FLOW_TYPE, DOMAIN, KEY_COORDINATOR, KEY_DEVICE
from .ng_number import XiaomiNumber

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Selectors from a config entry."""
    entities = []

    # TODO: why it is necessary to check for this?
    if not config_entry.data[CONF_FLOW_TYPE] == CONF_DEVICE:
        return

    device = hass.data[DOMAIN][config_entry.entry_id][KEY_DEVICE]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][KEY_COORDINATOR]

    # Handle switches defined by the backing class.
    for setting in device.settings().values():
        from miio.descriptors import SettingType

        if setting.type == SettingType.Number:
            _LOGGER.error("Adding new number setting: %s", setting)
            entities.append(XiaomiNumber(device, setting, config_entry, coordinator))

    async_add_entities(entities)
