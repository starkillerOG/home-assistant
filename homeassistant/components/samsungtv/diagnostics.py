"""Diagnostics support for SamsungTV."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant

from .const import CONF_IP_CONTROL_TOKEN, CONF_SESSION_ID
from .coordinator import SamsungTVConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_SESSION_ID, CONF_IP_CONTROL_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SamsungTVConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    diagnostics: dict[str, Any] = {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device_info": await coordinator.bridge.async_device_info(),
    }
    if coordinator.ip_control:
        diagnostics["ip_control_states"] = coordinator.ip_control.states
    return diagnostics
