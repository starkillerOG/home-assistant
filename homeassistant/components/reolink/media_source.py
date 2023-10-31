"""Expose Reolink IP camera VODs as media sources."""

from __future__ import annotations

import datetime as dt
import logging

from homeassistant.components.camera import DynamicStreamSettings
from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.components.stream import create_stream
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_media_source(hass: HomeAssistant) -> ReolinkVODMediaSource:
    """Set up camera media source."""
    return ReolinkVODMediaSource(hass)


class ReolinkVODMediaSource(MediaSource):
    """Provide Reolink camera VODs as media sources."""

    name: str = "Reolink"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize ReolinkVODMediaSource."""
        super().__init__(DOMAIN)
        self.hass = hass
        self.data = hass.data[DOMAIN]

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        if item.domain != DOMAIN:
            raise Unresolvable(f"Unknown domain '{item.domain}' of media item.")
        if not isinstance(item.identifier, str):
            raise Unresolvable(
                f"Could not resolve identifier '{item.identifier}' of media item."
            )

        identifier = item.identifier.split("/")
        if identifier[0] != "FILE":
            raise Unresolvable(f"Unknown media item '{item.identifier}'.")

        config_entry_id = identifier[1]
        channel = int(identifier[2])
        filename = identifier[3]

        host = self.data[config_entry_id].host
        mime_type, url = await host.api.get_vod_source(channel, filename, stream="main")
        url_log = f"{url.split('&user=')[0]}&user=xxxxx&password=xxxxx"
        _LOGGER.debug(
            "Opening VOD stream from %s: %s", host.api.camera_name(channel), url_log
        )

        stream = create_stream(self.hass, url, {}, DynamicStreamSettings())
        stream.add_provider("hls", timeout=3600)
        stream_url: str = stream.endpoint_url("hls")
        stream_url = stream_url.replace("master_", "")
        return PlayMedia(
            stream_url,
            mime_type,
        )

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Return media."""
        if item.domain != DOMAIN:
            raise Unresolvable(f"Unknown domain '{item.domain}' during browsing.")

        if item.identifier is None:
            return await self._generate_root()

        if not isinstance(item.identifier, str):
            raise Unresolvable(
                f"Could not resolve identifier '{item.identifier}' during browsing."
            )

        identifier = item.identifier.split("/")
        item_type = identifier[0]

        if item_type == "CAM":
            config_entry_id = identifier[1]
            channel = int(identifier[2])
            return await self._generate_camera_days(config_entry_id, channel)
        if item_type == "DAY":
            config_entry_id = identifier[1]
            channel = int(identifier[2])
            year = int(identifier[3])
            month = int(identifier[4])
            day = int(identifier[5])
            return await self._generate_camera_files(
                config_entry_id, channel, year, month, day
            )

        raise Unresolvable(f"Unknown media item '{item.identifier}' during browsing.")

    async def _generate_root(self):
        """Return all available reolink cameras as root browsing structure."""
        children = []

        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        for config_entry_id in self.data:
            channels = []
            entities = er.async_entries_for_config_entry(entity_reg, config_entry_id)
            for entity in entities:
                if entity.disabled or not entity.entity_id.startswith("camera."):
                    continue

                ch = entity.unique_id.split("_")[1]
                if ch in channels:
                    continue
                channels.append(ch)

                device = device_reg.async_get(entity.device_id)
                device_name = (
                    device.name_by_user
                    if device.name_by_user is not None
                    else device.name
                )

                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=f"CAM/{config_entry_id}/{ch}",
                        media_class=MediaClass.CHANNEL,
                        media_content_type=MediaType.PLAYLIST,
                        title=device_name,
                        thumbnail=f"/api/camera_proxy/{entity.entity_id}",
                        can_play=False,
                        can_expand=True,
                    )
                )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.APP,
            media_content_type="",
            title="Reolink",
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _generate_camera_days(self, config_entry_id: str, channel: int):
        """Return all days on which recordings are available for a reolink camera."""
        host = self.data[config_entry_id].host

        # We want today of the camera, not necessarily today of the server
        now = host.api.time()
        if not now:
            now = await host.api.async_get_time()
        start = now - dt.timedelta(days=31)
        end = now

        children = []
        _LOGGER.debug(
            "Requesting recording days of %s from %s to %s",
            host.api.camera_name(channel),
            start,
            end,
        )
        (statuses, _) = await host.api.request_vod_files(
            channel, start, end, status_only=True, stream="main"
        )
        for status in statuses:
            for day in status.days:
                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=f"DAY/{config_entry_id}/{channel}/{status.year}/{status.month}/{day}",
                        media_class=MediaClass.DIRECTORY,
                        media_content_type=MediaType.PLAYLIST,
                        title=f"{status.year}/{status.month}/{day}",
                        can_play=False,
                        can_expand=True,
                    )
                )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"DAYS/{config_entry_id}/{channel}",
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.PLAYLIST,
            title=host.api.camera_name(channel),
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _generate_camera_files(
        self, config_entry_id: str, channel: int, year: int, month: int, day: int
    ):
        """Return all recording files on a specific day of a Reolink camera."""
        host = self.data[config_entry_id].host

        start = dt.datetime(year, month, day, hour=0, minute=0, second=0)
        end = dt.datetime(year, month, day, hour=23, minute=59, second=59)

        children = []
        _LOGGER.debug(
            "Requesting VODs of %s on %s/%s/%s",
            host.api.camera_name(channel),
            year,
            month,
            day,
        )
        (_, vod_files) = await host.api.request_vod_files(
            channel, start, end, stream="main"
        )
        for file in vod_files:
            file_name = f"{file.start_time.time()} {file.duration}"
            if file.triggers != file.triggers.NONE:
                file_name += " " + " ".join(
                    str(trigger.name).title()
                    for trigger in file.triggers
                    if trigger != trigger.NONE
                )

            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"FILE/{config_entry_id}/{channel}/{file.file_name}",
                    media_class=MediaClass.VIDEO,
                    media_content_type=MediaType.VIDEO,
                    title=file_name,
                    can_play=True,
                    can_expand=False,
                )
            )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"FILES/{config_entry_id}/{channel}",
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.PLAYLIST,
            title=host.api.camera_name(channel),
            can_play=False,
            can_expand=True,
            children=children,
        )
