"""Expose Reolink IP camera VODs as media sources."""

from __future__ import annotations

import datetime as dt

from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant, callback

from .camera import ReolinkCamera
from .const import DOMAIN
from .view import ReoLinkCameraDownloadView, _async_get_camera_component
from homeassistant.components.stream import create_stream
from homeassistant.components.camera import DynamicStreamSettings
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.const import Platform

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
        print(item)
        if item.domain != DOMAIN:
            raise Unresolvable("Unknown domain.")
        if not isinstance(item.identifier, str):
            raise Unresolvable("Could not resolve identifier.")
        
        identifier = item.identifier.split("/")
        if identifier[0] != "FILE":
            raise Unresolvable("Unknown item")

        config_entry_id = identifier[1]
        channel = int(identifier[2])
        filename = identifier[3]

        host = self.data[config_entry_id].host
        mime_type, url = await host.api.get_vod_source(channel, filename, stream="main")

        stream = create_stream(self.hass, url, {}, DynamicStreamSettings())
        stream.add_provider("hls", timeout=3600)
        stream_url: str = stream.endpoint_url("hls")
        stream_url = stream_url.replace("master_", "")
        return PlayMedia(
            stream_url,
            mime_type,
        )
        #FOR A LATER PR, add download option.
        #return PlayMedia(
        #    ReoLinkCameraDownloadView.url.replace(":.*}", "}").format(
        #        entity_id=entity_id, filename=file_name
        #    ),
        #    "video/mp4",
        #)

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Return media."""
        if item.domain != DOMAIN:
            raise Unresolvable("Unknown domain.")
        
        if item.identifier is None:
            return await self._generate_root()
        
        if not isinstance(item.identifier, str):
            raise Unresolvable("Could not resolve identifier.")

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
            return await self._generate_camera_files(config_entry_id, channel, year, month, day)

        raise BrowseError("Unknown item")

    async def _generate_root(self):
        children = []

        # Get all reolink cameras and there identification
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
                device_name = device.name_by_user if device.name_by_user is not None else device.name

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
        host = self.data[config_entry_id].host

        # we want today of the camera, not necessarily today of the server
        now = host.api.time()
        if not now:
            now = await host.api.async_get_time()
        start = now - dt.timedelta(days=31)
        end = now

        children = []
        (statuses, _) = await host.api.request_vod_files(channel, start, end, status_only=True, stream="main")
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

    async def _generate_camera_files(self, config_entry_id: str, channel: int, year: int, month: int, day: int):
        host = self.data[config_entry_id].host

        start = dt.datetime(year, month, day, hour=0, minute=0, second=0)
        end = dt.datetime(year, month, day, hour=23, minute=59, second=59)

        children = []
        (_, vod_files) = await host.api.request_vod_files(channel, start, end, stream="main")
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
