"""Support for Xiaomi Smart WiFi Socket and Smart Power Strip."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_COORDINATOR, KEY_DEVICE
from .ng_switch import XiaomiSwitch

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Xiaomi Miio Switch"
DATA_KEY = "switch.xiaomi_miio"


KEY_CHANNEL = "channel"
GATEWAY_SWITCH_VARS = {
    "status_ch0": {KEY_CHANNEL: 0},
    "status_ch1": {KEY_CHANNEL: 1},
    "status_ch2": {KEY_CHANNEL: 2},
}

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.entity_ids})


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch from a config entry."""

    entities = []
    device = hass.data[DOMAIN][config_entry.entry_id][KEY_DEVICE]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][KEY_COORDINATOR]

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    # Handle switches defined by the backing class.
    switches = device.switches()
    _LOGGER.debug("Found switches: %s", len(device.switches()))
    for switch in switches.values():
        _LOGGER.info("Adding switch: %s", switch)
        entities.append(XiaomiSwitch(device, switch, config_entry, coordinator))

    async_add_entities(entities)
