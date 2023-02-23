"""This component provides support for Reolink select entities."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from reolink_aio.api import DayNightEnum, Host, SpotlightModeEnum

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ReolinkData
from .const import DOMAIN
from .entity import ReolinkCoordinatorEntity


@dataclass
class ReolinkSelectEntityDescriptionMixin:
    """Mixin values for Reolink select entities."""

    method: Callable[[Host, int | None, str], Any]


@dataclass
class ReolinkSelectEntityDescription(
    SelectEntityDescription, ReolinkSelectEntityDescriptionMixin
):
    """A class that describes select entities."""

    supported: Callable[[Host, int | None], bool] = lambda api, ch: True
    value: Callable[[Host, int | None], str] | None = None
    get_options: Callable[[Host, int | None], Any] | None = None


SELECT_ENTITIES = (
    ReolinkSelectEntityDescription(
        key="floodlight_mode",
        name="Floodlight mode",
        icon="mdi:spotlight-beam",
        translation_key="floodlight_mode",
        options=[mode.name for mode in SpotlightModeEnum],
        supported=lambda api, ch: api.supported(ch, "floodLight"),
        value=lambda api, ch: SpotlightModeEnum(api.whiteled_mode(ch)).name,
        method=lambda api, ch, name: api.set_whiteled(ch, mode=name),
    ),
    ReolinkSelectEntityDescription(
        key="day_night_mode",
        name="Day night mode",
        icon="mdi:theme-light-dark",
        translation_key="day_night_mode",
        options=[mode.name for mode in DayNightEnum],
        supported=lambda api, ch: api.supported(ch, "dayNight"),
        value=lambda api, ch: DayNightEnum(api.daynight_state(ch)).name,
        method=lambda api, ch, name: api.set_daynight(ch, DayNightEnum[name].value),
    ),
    ReolinkSelectEntityDescription(
        key="ptz_preset",
        name="PTZ preset",
        icon="mdi:pan",
        get_options=lambda api, ch: list(api.ptz_presets(ch).keys()),
        supported=lambda api, ch: api.supported(ch, "ptz_presets"),
        method=lambda api, ch, name: api.set_ptz_command(ch, preset=name),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Reolink select entities."""
    reolink_data: ReolinkData = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        ReolinkSelectEntity(reolink_data, channel, entity_description)
        for entity_description in SELECT_ENTITIES
        for channel in reolink_data.host.api.channels
        if entity_description.supported(reolink_data.host.api, channel)
    )


class ReolinkSelectEntity(ReolinkCoordinatorEntity, SelectEntity):
    """Base select entity class for Reolink IP cameras."""

    entity_description: ReolinkSelectEntityDescription

    def __init__(
        self,
        reolink_data: ReolinkData,
        channel: int,
        entity_description: ReolinkSelectEntityDescription,
    ) -> None:
        """Initialize Reolink select entity."""
        super().__init__(reolink_data, channel)
        self.entity_description = entity_description

        self._attr_unique_id = (
            f"{self._host.unique_id}_{self._channel}_{entity_description.key}"
        )

        if entity_description.get_options is not None:
            self._attr_options = entity_description.get_options(
                self._host.api, self._channel
            )

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        if self.entity_description.value is None:
            return None

        return self.entity_description.value(self._host.api, self._channel)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.method(self._host.api, self._channel, option)
