"""Coordinator for the SamsungTV integration."""

from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import TYPE_CHECKING, Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bridge import SamsungTVBridge
from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from .ip_control import SamsungTVIPControl

SCAN_INTERVAL = 10

type SamsungTVConfigEntry = ConfigEntry[SamsungTVDataUpdateCoordinator]


class SamsungTVDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Coordinator for the SamsungTV integration."""

    config_entry: SamsungTVConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SamsungTVConfigEntry,
        bridge: SamsungTVBridge,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )

        self.bridge = bridge
        self.ip_control: SamsungTVIPControl | None = None
        self.is_on: bool | None = None
        self.async_extra_update: Callable[[], Coroutine[Any, Any, None]] | None = None

    @override
    async def _async_update_data(self) -> None:
        """Fetch data from SamsungTV bridge."""
        if self.bridge.auth_failed:
            return
        old_state = self.is_on
        if self.bridge.power_off_in_progress:
            self.is_on = False
        else:
            self.is_on = await self.bridge.async_is_on()
        if self.is_on != old_state:
            LOGGER.debug(
                "TV %s state updated from %s to %s",
                self.bridge.host,
                old_state,
                self.is_on,
            )

        if self.ip_control and self.is_on:
            await self.ip_control.async_update()

        if self.async_extra_update:
            await self.async_extra_update()
