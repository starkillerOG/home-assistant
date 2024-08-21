"""Common fixtures for the SMLIGHT Zigbee tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

from pysmlight.web import Info, Sensors
import pytest

from homeassistant.components.smlight.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry, load_json_object_fixture

MOCK_HOST = "slzb-06.local"
MOCK_USERNAME = "test-user"
MOCK_PASSWORD = "test-pass"


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: MOCK_PASSWORD,
        },
        unique_id="aa:bb:cc:dd:ee:ff",
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.smlight.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_smlight_client(request: pytest.FixtureRequest) -> Generator[MagicMock]:
    """Mock the SMLIGHT API client."""
    with (
        patch(
            "homeassistant.components.smlight.coordinator.Api2", autospec=True
        ) as smlight_mock,
        patch("homeassistant.components.smlight.config_flow.Api2", new=smlight_mock),
    ):
        api = smlight_mock.return_value
        api.host = MOCK_HOST
        api.get_info.return_value = Info.from_dict(
            load_json_object_fixture("info.json", DOMAIN)
        )
        api.get_sensors.return_value = Sensors.from_dict(
            load_json_object_fixture("sensors.json", DOMAIN)
        )

        api.check_auth_needed.return_value = False
        api.authenticate.return_value = True

        yield api


async def setup_integration(hass: HomeAssistant, mock_config_entry: MockConfigEntry):
    """Set up the integration."""
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    return mock_config_entry
