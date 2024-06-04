"""Test the V2C sensor platform."""

from unittest.mock import AsyncMock, patch

from syrupy import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import init_integration

from tests.common import MockConfigEntry, snapshot_platform


async def test_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_v2c_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry_enabled_by_default: None,
) -> None:
    """Test states of the sensor."""
    with patch("homeassistant.components.v2c.PLATFORMS", [Platform.SENSOR]):
        await init_integration(hass, mock_config_entry)
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)

    from homeassistant.components.v2c.sensor import _METER_ERROR_OPTIONS

    assert [
        "no_error",
        "communication",
        "reading",
        "slave",
        "waiting_wifi",
        "waiting_communication",
        "wrong_ip",
        "slave_not_found",
        "wrong_slave",
        "no_response",
        "clamp_not_connected",
        "illegal_function",
        "illegal_data_address",
        "illegal_data_value",
        "server_device_failure",
        "acknowledge",
        "server_device_busy",
        "negative_acknowledge",
        "memory_parity_error",
        "gateway_path_unavailable",
        "gateway_target_no_resp",
        "server_rtu_inactive244_timeout",
        "invalid_server",
        "crc_error",
        "fc_mismatch",
        "server_id_mismatch",
        "packet_length_error",
        "parameter_count_error",
        "parameter_limit_error",
        "request_queue_full",
        "illegal_ip_or_port",
        "ip_connection_failed",
        "tcp_head_mismatch",
        "empty_message",
        "undefined_error",
    ] == _METER_ERROR_OPTIONS
