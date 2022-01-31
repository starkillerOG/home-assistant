"""Support for Netgear switches."""
import logging

from pynetgear import ALLOW, BLOCK

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .router import NetgearDeviceEntity, NetgearRouter, async_setup_netgear_entry

_LOGGER = logging.getLogger(__name__)


SWITCH_TYPES = [
    SwitchEntityDescription(
        key="allow_or_block",
        name="Allowed on network",
        icon="mdi:block-helper",
        entity_category=EntityCategory.CONFIG,
    )
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switches for Netgear component."""

    def generate_classes(
        coordinator: DataUpdateCoordinator, router: NetgearRouter, device: dict
    ):
        return [
            NetgearAllowBlock(coordinator, router, device, entity_description)
            for entity_description in SWITCH_TYPES
        ]

    async_setup_netgear_entry(hass, entry, async_add_entities, generate_classes)


class NetgearAllowBlock(NetgearDeviceEntity, SwitchEntity):
    """Allow or Block a device from the network."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        router: NetgearRouter,
        device: dict,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """Initialize a Netgear device."""
        super().__init__(coordinator, router, device)
        self.entity_description = entity_description
        self._name = f"{self.get_device_name()} {self.entity_description.name}"
        self._unique_id = f"{self._mac}-{self.entity_description.key}"
        self._state = True
        self.async_update_device()

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._state

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.hass.async_add_executor_job(
            self._router.api.allow_block_device, self._mac, ALLOW
        )

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.hass.async_add_executor_job(
            self._router.api.allow_block_device, self._mac, BLOCK
        )

    @callback
    def async_update_device(self) -> None:
        """Update the Netgear device."""
        self._device = self._router.devices[self._mac]
        self._active = self._device["active"]
        self._state = self._device[self.entity_description.key] == "Allow"
