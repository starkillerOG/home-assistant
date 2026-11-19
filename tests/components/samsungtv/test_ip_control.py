"""Tests for the IP control (IP remote) support of the samsungtv component."""

from unittest.mock import Mock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant.typing import ClientSessionGenerator
from samsungtvws.exceptions import (
    ConnectionFailure,
    IPControlConnectionError,
    IPControlError,
    IPControlResponseError,
    IPControlUnauthorizedError,
)
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from homeassistant import config_entries
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    DOMAIN as MP_DOMAIN,
    SERVICE_SELECT_SOURCE,
    MediaPlayerEntityFeature,
)
from homeassistant.components.samsungtv.const import (
    CONF_IP_CONTROL_TOKEN,
    DOMAIN,
    ENTRY_RELOAD_COOLDOWN,
)
from homeassistant.components.samsungtv.coordinator import SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    CONF_HOST,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from . import setup_samsungtv_entry
from .const import ENTRYDATA_WEBSOCKET, ENTRYDATA_WEBSOCKET_IP_CONTROL

ENTITY_ID = f"{MP_DOMAIN}.mock_title"
MOCK_USER_DATA = {CONF_HOST: "fake_host"}


@pytest.fixture(name="ip_control_enabled")
def ip_control_enabled_fixture(ip_control: Mock) -> Mock:
    """Mock a TV with the IP remote setting enabled."""
    ip_control.send_request.side_effect = IPControlResponseError(
        "Parse error", code=-32700
    )
    return ip_control


async def _async_start_user_flow(
    hass: HomeAssistant,
) -> config_entries.ConfigFlowResult:
    """Run the user flow until the websocket pairing is done."""
    with patch(
        "homeassistant.components.samsungtv.bridge.SamsungTVLegacyAsyncRemote.open",
        side_effect=ConnectionFailure("Boom"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_DATA
        )


@pytest.mark.usefixtures(
    "remote_websocket", "rest_api", "remote_encrypted_websocket_failing"
)
async def test_user_flow_pairing(
    hass: HomeAssistant, ip_control_enabled: Mock, mock_setup_entry: Mock
) -> None:
    """Test pairing with IP control in the user flow."""
    result = await _async_start_user_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "ip_control"
    assert result["menu_options"] == ["ip_control_pairing", "ip_control_skip"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "ip_control_pairing"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "ip_control_pairing"
    assert result["errors"] == {}
    ip_control_enabled.create_access_token.assert_not_called()

    # The popup on the TV is not accepted
    ip_control_enabled.create_access_token.side_effect = IPControlError
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "ip_control_pairing"
    assert result["errors"] == {"base": "ip_control_pairing_failed"}

    ip_control_enabled.create_access_token.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "10.20.43.21"
    assert result["data"][CONF_IP_CONTROL_TOKEN] == "IP_CONTROL_TOKEN"


@pytest.mark.usefixtures(
    "remote_websocket",
    "rest_api",
    "remote_encrypted_websocket_failing",
    "ip_control_enabled",
    "mock_setup_entry",
)
async def test_user_flow_skip(hass: HomeAssistant) -> None:
    """Test skipping the IP control pairing in the user flow."""
    result = await _async_start_user_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "ip_control"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "ip_control_skip"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_IP_CONTROL_TOKEN not in result["data"]


@pytest.mark.usefixtures(
    "remote_websocket", "rest_api", "remote_encrypted_websocket_failing"
)
async def test_user_flow_available_without_error(
    hass: HomeAssistant, ip_control: Mock, mock_setup_entry: Mock
) -> None:
    """Test IP control is offered if the TV answers the availability check."""
    ip_control.send_request.side_effect = None
    result = await _async_start_user_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "ip_control"


@pytest.mark.parametrize(
    ("next_step", "user_inputs", "expected_token"),
    [
        ("ip_control_pairing", [{}], "IP_CONTROL_TOKEN"),
        ("ip_control_skip", [], None),
    ],
)
@pytest.mark.usefixtures("ip_control_enabled", "mock_setup_entry")
async def test_reconfigure(
    hass: HomeAssistant,
    next_step: str,
    user_inputs: list[dict[str, str]],
    expected_token: str | None,
) -> None:
    """Test the IP control pairing in the reconfigure flow."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRYDATA_WEBSOCKET)
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == config_entries.SOURCE_RECONFIGURE

    with patch(
        "homeassistant.components.samsungtv.config_flow.socket.gethostbyname",
        return_value="10.10.12.77",
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "new-host"}
        )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "ip_control"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": next_step}
    )
    for user_input in user_inputs:
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "10.10.12.77"
    assert entry.data.get(CONF_IP_CONTROL_TOKEN) == expected_token


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_not_paired(hass: HomeAssistant, ip_control: Mock) -> None:
    """Test IP control is not used without pairing."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INPUT_SOURCE_LIST] == ["TV", "HDMI"]
    assert ATTR_INPUT_SOURCE not in state.attributes
    assert not (
        state.attributes[ATTR_SUPPORTED_FEATURES] & MediaPlayerEntityFeature.TURN_ON
    )
    ip_control.get_tv_states.assert_not_called()


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_source(
    hass: HomeAssistant, ip_control: Mock, freezer: FrozenDateTimeFactory
) -> None:
    """Test the selected source is updated from the TV."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INPUT_SOURCE] == "HDMI1"
    assert state.attributes[ATTR_INPUT_SOURCE_LIST] == [
        "TV",
        "HDMI",
        "HDMI1",
        "HDMI2",
        "HDMI3",
        "HDMI4",
    ]
    assert state.attributes[ATTR_SUPPORTED_FEATURES] & MediaPlayerEntityFeature.TURN_ON

    ip_control.get_tv_states.return_value = {"inputSource": "HDMI2"}
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI2"

    # The source is unknown while IP control fails, and is restored afterwards
    ip_control.get_tv_states.side_effect = IPControlConnectionError
    for _ in range(2):
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ON
        assert ATTR_INPUT_SOURCE not in state.attributes

    ip_control.get_tv_states.side_effect = None
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI2"


@pytest.mark.usefixtures("rest_api")
async def test_source_unknown_when_off(
    hass: HomeAssistant,
    ip_control: Mock,
    remote_websocket: Mock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the TV is not polled and has no source when turned off."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI1"
    ip_control.get_tv_states.reset_mock()

    with patch(
        "homeassistant.components.samsungtv.bridge.SamsungTVWSBridge.async_is_on",
        return_value=False,
    ):
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert ATTR_INPUT_SOURCE not in state.attributes
    ip_control.get_tv_states.assert_not_called()


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_select_source(hass: HomeAssistant, ip_control: Mock) -> None:
    """Test selecting a HDMI source."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)

    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_INPUT_SOURCE: "HDMI3"},
        True,
    )
    ip_control.input_source_control.assert_called_once_with("HDMI3")
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI3"

    ip_control.input_source_control.side_effect = IPControlConnectionError("Boom")
    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            MP_DOMAIN,
            SERVICE_SELECT_SOURCE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_INPUT_SOURCE: "HDMI4"},
            True,
        )
    assert exc_info.value.translation_key == "error_sending_command"
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI3"


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_select_hdmi_source_not_paired(hass: HomeAssistant) -> None:
    """Test a HDMI source can not be selected without IP control."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET)

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            MP_DOMAIN,
            SERVICE_SELECT_SOURCE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_INPUT_SOURCE: "HDMI1"},
            True,
        )
    assert exc_info.value.translation_key == "source_unsupported"


@pytest.mark.parametrize(
    "side_effect",
    [
        None,
        # Reported by some models in standby, while still turning on
        IPControlResponseError("Failed", code=-32002),
    ],
)
@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_turn_on(
    hass: HomeAssistant, ip_control: Mock, side_effect: Exception | None
) -> None:
    """Test turning on the TV."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)
    ip_control.power_on.side_effect = side_effect

    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, True
    )
    ip_control.power_on.assert_called_once_with()


@pytest.mark.parametrize(
    "side_effect",
    [
        IPControlConnectionError("Boom"),
        IPControlResponseError("Not supported", code=-32001),
    ],
)
@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_turn_on_error(
    hass: HomeAssistant, ip_control: Mock, side_effect: Exception
) -> None:
    """Test errors while turning on the TV."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)
    ip_control.power_on.side_effect = side_effect

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, True
        )
    assert exc_info.value.translation_key == "error_sending_command"


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_reauth_on_update(
    hass: HomeAssistant, ip_control: Mock, freezer: FrozenDateTimeFactory
) -> None:
    """Test pairing again when the access token is rejected."""
    entry = await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI1"

    ip_control.get_tv_states.side_effect = IPControlUnauthorizedError
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert ATTR_INPUT_SOURCE not in state.attributes
    assert ip_control.get_tv_states.call_count == 2

    # The TV is no longer polled until paired again
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert ip_control.get_tv_states.call_count == 2

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flows[0]["step_id"] == "reauth_ip_control"

    ip_control.create_access_token.side_effect = IPControlError
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_ip_control"
    assert result["errors"] == {"base": "ip_control_pairing_failed"}

    ip_control.create_access_token.side_effect = None
    ip_control.create_access_token.return_value = "NEW_TOKEN"
    ip_control.get_tv_states.side_effect = None
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_IP_CONTROL_TOKEN] == "NEW_TOKEN"

    # The entry is reloaded by the update listener
    freezer.tick(ENTRY_RELOAD_COOLDOWN)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).attributes[ATTR_INPUT_SOURCE] == "HDMI1"


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_reauth_on_command(hass: HomeAssistant, ip_control: Mock) -> None:
    """Test a reauth flow is started when a command is rejected."""
    await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)
    ip_control.power_on.side_effect = IPControlUnauthorizedError("Rejected")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, True
        )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_ip_control"

    # Only a single reauth flow is started
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, True
        )
    await hass.async_block_till_done()
    assert len(hass.config_entries.flow.async_progress_by_handler(DOMAIN)) == 1


@pytest.mark.usefixtures("remote_websocket", "rest_api")
async def test_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics with IP control."""
    config_entry = await setup_samsungtv_entry(hass, ENTRYDATA_WEBSOCKET_IP_CONTROL)

    assert await get_diagnostics_for_config_entry(
        hass, hass_client, config_entry
    ) == snapshot(exclude=props("created_at", "modified_at"))
