"""Reolink Integration views."""

import secrets

from aiohttp import web
from reolink_aio.baichuan.media_decoder import HLS_PLAYLIST

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.media_source import Unresolvable
from homeassistant.core import HomeAssistant, callback

from .util import get_host


@callback
def async_generate_hls_url(config_entry_id: str, token: str) -> str:
    """Generate the URL of the HLS playlist of a recording being downloaded."""
    return HlsPlaybackView.url.format(
        config_entry_id=config_entry_id, token=token, filename=HLS_PLAYLIST
    )


class HlsPlaybackView(HomeAssistantView):
    """View to serve the HLS files of a Reolink recording being downloaded."""

    # The HLS player does not authenticate the requests for the files in the
    # playlist, the random token of the playback is used instead.
    requires_auth = False
    url = "/api/reolink/hls/{config_entry_id}/{token}/{filename}"
    name = "api:reolink_hls"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the HLS view."""
        self.hass = hass

    async def get(
        self, request: web.Request, config_entry_id: str, token: str, filename: str
    ) -> web.FileResponse:
        """Return a HLS file, wait for it when it is not downloaded yet."""
        try:
            playback = get_host(self.hass, config_entry_id).hls_playback
        except Unresolvable:
            playback = None
        if playback is None or not secrets.compare_digest(playback.token, token):
            raise web.HTTPNotFound

        path = await playback.async_get_file(filename)
        if path is None:
            raise web.HTTPNotFound

        if filename == HLS_PLAYLIST:
            content_type = "application/vnd.apple.mpegurl"
        else:
            content_type = "video/mp4"
        return web.FileResponse(path, headers={"Content-Type": content_type})
