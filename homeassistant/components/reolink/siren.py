"""Component providing support for Reolink siren entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reolink_aio.exceptions import InvalidParameterError, ReolinkError
from reolink_aio.api import Chime

from homeassistant.components.siren import (
    ATTR_DURATION,
    ATTR_VOLUME_LEVEL,
    ATTR_TONE,
    SirenEntity,
    SirenEntityDescription,
    SirenEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ReolinkData
from .const import DOMAIN
from .entity import ReolinkChannelCoordinatorEntity, ReolinkChannelEntityDescription, ReolinkChimeCoordinatorEntity


@dataclass(frozen=True)
class ReolinkSirenEntityDescription(
    SirenEntityDescription, ReolinkChannelEntityDescription
):
    """A class that describes siren entities."""


SIREN_ENTITIES = (
    ReolinkSirenEntityDescription(
        key="siren",
        translation_key="siren",
        supported=lambda api, ch: api.supported(ch, "siren_play"),
    ),
)

CHIME_SIREN_ENTITIES = (
    ReolinkSirenEntityDescription(
        key="play_ringtone",
        translation_key="play_ringtone",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Reolink siren entities."""
    reolink_data: ReolinkData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[ReolinkSirenEntity | ReolinkChimeSirenEntity] = [
        ReolinkSirenEntity(reolink_data, channel, entity_description)
        for entity_description in SIREN_ENTITIES
        for channel in reolink_data.host.api.channels
        if entity_description.supported(reolink_data.host.api, channel)
    ]
    entities.extend(
        ReolinkChimeSirenEntity(reolink_data, chime, entity_description)
        for entity_description in CHIME_SIREN_ENTITIES
        for chime in reolink_data.host.api.chime_list
    )
    async_add_entities(entities)


class ReolinkSirenEntity(ReolinkChannelCoordinatorEntity, SirenEntity):
    """Base siren entity class for Reolink IP cameras."""

    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
        | SirenEntityFeature.VOLUME_SET
    )
    entity_description: ReolinkSirenEntityDescription

    def __init__(
        self,
        reolink_data: ReolinkData,
        channel: int,
        entity_description: ReolinkSirenEntityDescription,
    ) -> None:
        """Initialize Reolink siren entity."""
        self.entity_description = entity_description
        super().__init__(reolink_data, channel)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the siren."""
        if (volume := kwargs.get(ATTR_VOLUME_LEVEL)) is not None:
            try:
                await self._host.api.set_volume(self._channel, int(volume * 100))
            except InvalidParameterError as err:
                raise ServiceValidationError(err) from err
            except ReolinkError as err:
                raise HomeAssistantError(err) from err
        duration = kwargs.get(ATTR_DURATION)
        try:
            await self._host.api.set_siren(self._channel, True, duration)
        except InvalidParameterError as err:
            raise ServiceValidationError(err) from err
        except ReolinkError as err:
            raise HomeAssistantError(err) from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the siren."""
        try:
            await self._host.api.set_siren(self._channel, False, None)
        except ReolinkError as err:
            raise HomeAssistantError(err) from err


class ReolinkChimeSirenEntity(ReolinkChimeCoordinatorEntity, SirenEntity):
    """Base siren entity class for Reolink IP cameras."""

    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.VOLUME_SET
        | SirenEntityFeature.TONES
    )
    entity_description: ReolinkSirenEntityDescription

    def __init__(
        self,
        reolink_data: ReolinkData,
        chime: Chime,
        entity_description: ReolinkChannelEntityDescription,
    ) -> None:
        """Initialize Reolink siren entity for a chime."""
        self.entity_description = entity_description
        super().__init__(reolink_data, chime)
        self._attr_available_tones = [method.name for method in ChimeToneEnum][1:]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the siren."""
        if (volume := kwargs.get(ATTR_VOLUME_LEVEL)) is not None:
            try:
                await self._chime.set_option(volume = int(volume * 4))
            except InvalidParameterError as err:
                raise ServiceValidationError(err) from err
            except ReolinkError as err:
                raise HomeAssistantError(err) from err
            self.async_write_ha_state()

        ringtone = kwargs.get(ATTR_TONE)
        for event in ["visitor", "people", "package", "md"]:
            if ringtone is None:
                ringtone = self._chime.tone(event)
        if ringtone is None:
            ringtone = 0
        try:
            await self._chime.play(ringtone)
        except InvalidParameterError as err:
            raise ServiceValidationError(err) from err
        except ReolinkError as err:
            raise HomeAssistantError(err) from err
