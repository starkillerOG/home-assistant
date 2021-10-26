"""Test the Goodwe config flow."""
import socket
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.goodwe import const
from homeassistant import config_entries
from homeassistant.const import CONF_HOST

TEST_HOST = "1.2.3.4"
TEST_SERIAL = "123456789"

@pytest.fixture(name="goodwe_connect", autouse=True)
def goodwe_connect_fixture():
    """Mock motion blinds connection and entry setup."""
    goodwe_inverter = AsyncMock()
    goodwe_inverter.serial_number = TEST_SERIAL

    with patch(
        "homeassistant.components.goodwe.connect",
        return_value=goodwe_inverter,
    ), patch(
        "homeassistant.components.goodwe.async_setup_entry", return_value=True
    ):
        yield


async def test_config_flow_manual_host_success(hass):
    """Successful flow manually initialized by the user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: TEST_HOST},
    )

    assert result["type"] == "create_entry"
    assert result["title"] == const.DEFAULT_NAME
    assert result["data"] == {
        CONF_HOST: TEST_HOST,
        const.CONF_MODEL_FAMILY: "Mock",
    }
