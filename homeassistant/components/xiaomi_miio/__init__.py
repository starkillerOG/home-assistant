"""Support for Xiaomi Miio."""
from __future__ import annotations

from datetime import timedelta
import logging

import async_timeout
from miio import Device as MiioDevice, DeviceException, DeviceFactory
from miio.interfaces import VacuumInterface

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_AVAILABLE,
    CONF_DEVICE,
    CONF_FLOW_TYPE,
    CONF_GATEWAY,
    DOMAIN,
    KEY_COORDINATOR,
    KEY_DEVICE,
    MODELS_AIR_MONITOR,
    MODELS_FAN,
    MODELS_HUMIDIFIER,
    MODELS_LIGHT,
    MODELS_SWITCH,
    MODELS_VACUUM,
    AuthException,
    SetupException,
)
from .gateway import ConnectXiaomiGateway

_LOGGER = logging.getLogger(__name__)

POLLING_TIMEOUT_SEC = 10
UPDATE_INTERVAL = timedelta(seconds=15)

# List of common platforms initialized for all supported devices
COMMON_PLATFORMS = {
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
}

GATEWAY_PLATFORMS = {
    Platform.ALARM_CONTROL_PANEL,
    Platform.LIGHT,
}
SWITCH_PLATFORMS: set[str] = set()
FAN_PLATFORMS = {
    Platform.FAN,
}
HUMIDIFIER_PLATFORMS = {
    Platform.HUMIDIFIER,
}
LIGHT_PLATFORMS = {Platform.LIGHT}
VACUUM_PLATFORMS = {
    Platform.VACUUM,
}
AIR_MONITOR_PLATFORMS = {Platform.AIR_QUALITY}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Xiaomi Miio components from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    if entry.data[CONF_FLOW_TYPE] == CONF_GATEWAY:
        # TODO: convert gateway to use the common facilities
        await async_setup_gateway_entry(hass, entry)
        return True

    return bool(
        entry.data[CONF_FLOW_TYPE] != CONF_DEVICE
        or await async_setup_device_entry(hass, entry)
    )


@callback
def get_platforms(hass, config_entry):
    """Return the platforms belonging to a config_entry."""
    model = config_entry.data[CONF_MODEL]
    flow_type = config_entry.data[CONF_FLOW_TYPE]
    device = hass.data[DOMAIN][config_entry.entry_id][KEY_DEVICE]

    if flow_type == CONF_GATEWAY:
        return GATEWAY_PLATFORMS | COMMON_PLATFORMS

    if isinstance(device, VacuumInterface):
        return COMMON_PLATFORMS | {Platform.VACUUM}

    """
    if isinstance(device, LightInterface):
        _LOGGER.error("woot, got light")
        return COMMON_PLATFORMS | {Platform.LIGHT}
    """

    # TODO: remove the legacy below
    # TODO: we need to check the device type to choose which "special" platforms to initialize
    if flow_type == CONF_DEVICE:
        if model in MODELS_SWITCH:
            return SWITCH_PLATFORMS | COMMON_PLATFORMS
        if model in MODELS_HUMIDIFIER:
            return HUMIDIFIER_PLATFORMS | COMMON_PLATFORMS
        if model in MODELS_FAN:
            return FAN_PLATFORMS | COMMON_PLATFORMS
        if model in MODELS_LIGHT:
            return LIGHT_PLATFORMS | COMMON_PLATFORMS
        for vacuum_model in MODELS_VACUUM:
            if model.startswith(vacuum_model):
                return VACUUM_PLATFORMS | COMMON_PLATFORMS
        for air_monitor_model in MODELS_AIR_MONITOR:
            if model.startswith(air_monitor_model):
                return AIR_MONITOR_PLATFORMS | COMMON_PLATFORMS

    _LOGGER.error(
        "Found a platform with no type designation, please report %s "
        "and expected platform to %s",
        model,
        "https://github.com/rytilahti/python-miio/issues",
    )

    return COMMON_PLATFORMS


def _async_update_data_default(hass, device):
    async def update():
        """Fetch data from the device using async_add_executor_job."""

        async def _async_fetch_data():
            """Fetch data from the device."""
            async with async_timeout.timeout(POLLING_TIMEOUT_SEC):
                state = await hass.async_add_executor_job(device.status)
                _LOGGER.debug("Got new state: %s", state)
                return state

        try:
            return await _async_fetch_data()
        except DeviceException as ex:
            if getattr(ex, "code", None) != -9999:
                raise UpdateFailed(ex) from ex
            _LOGGER.info("Got exception while fetching the state, trying again: %s", ex)
        # Try to fetch the data a second time after error code -9999
        try:
            return await _async_fetch_data()
        except DeviceException as ex:
            raise UpdateFailed(ex) from ex

    return update


async def async_create_miio_device_and_coordinator(
    hass: HomeAssistant, entry: ConfigEntry
) -> set[Platform]:
    """Set up a data coordinator and one miio device to service multiple entities."""
    model: str = entry.data[CONF_MODEL]
    host = entry.data[CONF_HOST]
    token = entry.data[CONF_TOKEN]
    name = entry.title
    device: MiioDevice | None = None
    update_method = _async_update_data_default
    coordinator_class: type[DataUpdateCoordinator] = DataUpdateCoordinator

    _LOGGER.debug("Initializing with host %s (token %s...)", host, token[:5])

    try:
        device = DeviceFactory.create(host, token, model=model)
    except DeviceException:
        _LOGGER.warning("Tried to initialize unsupported %s, skipping", model)
        raise

    # Create update miio device and coordinator
    coordinator = coordinator_class(
        hass,
        _LOGGER,
        name=name,
        update_method=update_method(hass, device),
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=UPDATE_INTERVAL,
    )
    hass.data[DOMAIN][entry.entry_id] = {
        KEY_DEVICE: device,
        KEY_COORDINATOR: coordinator,
    }

    # Trigger first data fetch
    await coordinator.async_config_entry_first_refresh()

    return get_platforms(hass, entry)


async def async_setup_gateway_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the Xiaomi Gateway component from a config entry."""
    host = entry.data[CONF_HOST]
    token = entry.data[CONF_TOKEN]
    name = entry.title
    gateway_id = entry.unique_id

    assert gateway_id

    # For backwards compat
    if gateway_id.endswith("-gateway"):
        hass.config_entries.async_update_entry(entry, unique_id=entry.data["mac"])

    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Connect to gateway
    gateway = ConnectXiaomiGateway(hass, entry)
    try:
        await gateway.async_connect_gateway(host, token)
    except AuthException as error:
        raise ConfigEntryAuthFailed() from error
    except SetupException as error:
        raise ConfigEntryNotReady() from error
    gateway_info = gateway.gateway_info

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, gateway_info.mac_address)},
        identifiers={(DOMAIN, gateway_id)},
        manufacturer="Xiaomi",
        name=name,
        model=gateway_info.model,
        sw_version=gateway_info.firmware_version,
        hw_version=gateway_info.hardware_version,
    )

    def update_data_factory(sub_device):
        """Create update function for a subdevice."""

        async def async_update_data():
            """Fetch data from the subdevice."""
            try:
                await hass.async_add_executor_job(sub_device.update)
            except DeviceException as ex:
                _LOGGER.error("Got exception while fetching the state: %s", ex)
                return {ATTR_AVAILABLE: False}
            return {ATTR_AVAILABLE: True}

        return async_update_data

    coordinator_dict: dict[str, DataUpdateCoordinator] = {}
    for sub_device in gateway.gateway_device.devices.values():
        # Create update coordinator
        coordinator_dict[sub_device.sid] = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=name,
            update_method=update_data_factory(sub_device),
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=UPDATE_INTERVAL,
        )

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_GATEWAY: gateway.gateway_device,
        KEY_COORDINATOR: coordinator_dict,
    }

    await hass.config_entries.async_forward_entry_setups(entry, GATEWAY_PLATFORMS)


async def async_setup_device_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Xiaomi Miio device component from a config entry."""
    platforms = await async_create_miio_device_and_coordinator(hass, entry)

    if not platforms:
        return False

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = get_platforms(hass, config_entry)

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, platforms
    )

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
