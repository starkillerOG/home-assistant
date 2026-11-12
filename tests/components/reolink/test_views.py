"""Tests for the Reolink views platform."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, cast
from unittest.mock import MagicMock, patch

from aiohttp import ClientResponse
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.typing import ClientSessionGenerator
from reolink_aio.baichuan.media_decoder import HLS_INIT, HLS_PLAYLIST
from reolink_aio.exceptions import UnexpectedDataError

from homeassistant.components.reolink.hls import IDLE_TIMEOUT, ReolinkHlsPlayback
from homeassistant.components.reolink.views import async_generate_hls_url
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

TEST_STREAM = "sub"
TEST_CHANNEL = "0"
TEST_ERROR = "TestError"
TEST_HLS_START = datetime(2023, 11, 14, 13, 12, 0)
TEST_HLS_END = datetime(2023, 11, 14, 13, 17, 0)
TEST_HLS_SEGMENT = "0.m4s"


async def start_hls_playback(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    stream_hls: Any,
) -> tuple[ReolinkHlsPlayback, str]:
    """Set up the config entry and start a HLS playback.

    Returns the playback and the URL of its playlist.
    """
    reolink_host.baichuan.stream_hls = MagicMock(side_effect=stream_hls)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    playback = await config_entry.runtime_data.host.async_start_hls_playback(
        int(TEST_CHANNEL), TEST_STREAM, TEST_HLS_START, TEST_HLS_END
    )
    return playback, async_generate_hls_url(config_entry.entry_id, playback.token)


async def test_hls_playback(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test serving the HLS files of a recording."""

    async def stream_hls(*args: Any) -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"playlist"
        yield HLS_INIT, b"init"
        yield TEST_HLS_SEGMENT, b"segment"

    _, playlist_url = await start_hls_playback(
        hass, reolink_host, config_entry, stream_hls
    )
    reolink_host.baichuan.stream_hls.assert_called_once_with(
        int(TEST_CHANNEL), TEST_HLS_START, TEST_HLS_END, TEST_STREAM, "ffmpeg"
    )

    http_client = await hass_client_no_auth()
    response = cast(ClientResponse, await http_client.get(playlist_url))
    assert response.status == HTTPStatus.OK
    assert response.content_type == "application/vnd.apple.mpegurl"
    assert await response.read() == b"playlist"

    for filename, content in ((HLS_INIT, b"init"), (TEST_HLS_SEGMENT, b"segment")):
        url = playlist_url.replace(HLS_PLAYLIST, filename)
        response = cast(ClientResponse, await http_client.get(url))
        assert response.status == HTTPStatus.OK
        assert response.content_type == "video/mp4"
        assert await response.read() == content

    # a file that is not part of the finished download
    url = playlist_url.replace(HLS_PLAYLIST, "1.m4s")
    response = cast(ClientResponse, await http_client.get(url))
    assert response.status == HTTPStatus.NOT_FOUND


async def test_hls_playback_wait_for_download(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test a request for a HLS file waits until the file is downloaded."""
    downloaded = asyncio.Event()

    async def stream_hls(*args: Any) -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"playlist"
        await downloaded.wait()
        yield TEST_HLS_SEGMENT, b"segment"

    _, playlist_url = await start_hls_playback(
        hass, reolink_host, config_entry, stream_hls
    )

    http_client = await hass_client_no_auth()
    url = playlist_url.replace(HLS_PLAYLIST, TEST_HLS_SEGMENT)
    request = hass.async_create_task(http_client.get(url))
    await asyncio.sleep(0.1)
    assert not request.done()

    downloaded.set()
    response = cast(ClientResponse, await request)
    assert response.status == HTTPStatus.OK
    assert await response.read() == b"segment"


async def test_hls_playback_timeout(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test a request for a HLS file which is not downloaded in time."""

    async def stream_hls(*args: Any) -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"playlist"
        await asyncio.Event().wait()

    _, playlist_url = await start_hls_playback(
        hass, reolink_host, config_entry, stream_hls
    )

    http_client = await hass_client_no_auth()
    url = playlist_url.replace(HLS_PLAYLIST, TEST_HLS_SEGMENT)
    with patch("homeassistant.components.reolink.hls.FILE_TIMEOUT", 0):
        response = cast(ClientResponse, await http_client.get(url))
    assert response.status == HTTPStatus.NOT_FOUND


async def test_hls_playback_download_error(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an error while downloading the recording."""

    async def stream_hls(*args: Any) -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"playlist"
        raise UnexpectedDataError(TEST_ERROR)

    _, playlist_url = await start_hls_playback(
        hass, reolink_host, config_entry, stream_hls
    )

    http_client = await hass_client_no_auth()
    url = playlist_url.replace(HLS_PLAYLIST, TEST_HLS_SEGMENT)
    response = cast(ClientResponse, await http_client.get(url))
    assert response.status == HTTPStatus.NOT_FOUND
    assert "Reolink playback error while downloading" in caplog.text


async def test_hls_playback_invalid_url(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test the HLS view with a wrong token or config entry id."""

    async def stream_hls(*args: Any) -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"playlist"

    playback, _ = await start_hls_playback(hass, reolink_host, config_entry, stream_hls)

    http_client = await hass_client_no_auth()
    for url in (
        async_generate_hls_url(config_entry.entry_id, "wrong_token"),
        async_generate_hls_url("wrong_config_entry_id", playback.token),
    ):
        response = cast(ClientResponse, await http_client.get(url))
        assert response.status == HTTPStatus.NOT_FOUND


async def test_hls_playback_stop_previous(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test a new HLS playback stops the previous one.

    A Reolink device allows only one download at a time.
    """
    first_closed = asyncio.Event()

    async def first_stream() -> AsyncGenerator[tuple[str, bytes]]:
        try:
            yield HLS_PLAYLIST, b"first"
            await asyncio.Event().wait()
        finally:
            first_closed.set()

    async def second_stream() -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"second"

    _, first_url = await start_hls_playback(
        hass, reolink_host, config_entry, [first_stream(), second_stream()]
    )

    http_client = await hass_client_no_auth()
    response = cast(ClientResponse, await http_client.get(first_url))
    assert await response.read() == b"first"
    assert not first_closed.is_set()

    host = config_entry.runtime_data.host
    second = await host.async_start_hls_playback(
        int(TEST_CHANNEL), TEST_STREAM, TEST_HLS_START, TEST_HLS_END
    )
    assert first_closed.is_set()

    response = cast(ClientResponse, await http_client.get(first_url))
    assert response.status == HTTPStatus.NOT_FOUND

    second_url = async_generate_hls_url(config_entry.entry_id, second.token)
    response = cast(ClientResponse, await http_client.get(second_url))
    assert await response.read() == b"second"


async def test_hls_playback_idle(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test the downloaded HLS files are removed when no longer requested."""

    async def stream_hls(*args: Any) -> AsyncGenerator[tuple[str, bytes]]:
        yield HLS_PLAYLIST, b"playlist"

    _, playlist_url = await start_hls_playback(
        hass, reolink_host, config_entry, stream_hls
    )

    http_client = await hass_client_no_auth()
    response = cast(ClientResponse, await http_client.get(playlist_url))
    assert response.status == HTTPStatus.OK

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=IDLE_TIMEOUT))
    await hass.async_block_till_done()

    response = cast(ClientResponse, await http_client.get(playlist_url))
    assert response.status == HTTPStatus.NOT_FOUND
