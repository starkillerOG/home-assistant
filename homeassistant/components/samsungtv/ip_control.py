"""IP control (IP Remote) support for the Samsung TV integration.

The IP control API is a local JSON-RPC service on port 1516, which needs to
be enabled on the TV. It can report and select the HDMI input and can turn
on the TV, which the websocket API does not support.
"""

from typing import Any

from samsungtvws.async_ip_control import ERROR_FAILED, SamsungTVAsyncIPControl
from samsungtvws.exceptions import (
    IPControlConnectionError,
    IPControlError,
    IPControlResponseError,
    IPControlUnauthorizedError,
)

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_IP_CONTROL_TOKEN,
    DOMAIN,
    LOGGER,
    TIMEOUT_IP_CONTROL,
    TIMEOUT_IP_CONTROL_PAIRING,
)
from .coordinator import SamsungTVConfigEntry

IP_CONTROL_SOURCES = ("HDMI1", "HDMI2", "HDMI3", "HDMI4")

# Key added to the reauth data, to pair again with the IP control API
REAUTH_IP_CONTROL = "reauth_ip_control"

KEY_INPUT_SOURCE = "inputSource"


def _async_get_client(
    hass: HomeAssistant, host: str, token: str | None = None
) -> SamsungTVAsyncIPControl:
    """Get an IP control client."""
    return SamsungTVAsyncIPControl(
        host,
        session=async_get_clientsession(hass),
        token=token,
        timeout=TIMEOUT_IP_CONTROL,
    )


async def async_ip_control_is_available(hass: HomeAssistant, host: str) -> bool:
    """Return if the IP control API is enabled on the TV."""
    client = _async_get_client(hass, host)
    try:
        # Any answer means the service is running, this does not show
        # a prompt on the TV and will be rejected without access token.
        await client.send_request("getTVStates", with_token=False)
    except IPControlConnectionError:
        return False
    except IPControlError:
        return True
    return True


async def async_ip_control_pair(hass: HomeAssistant, host: str) -> str | None:
    """Pair with the IP control API, the user needs to accept this on the TV."""
    client = _async_get_client(hass, host)
    try:
        return await client.create_access_token(timeout=TIMEOUT_IP_CONTROL_PAIRING)
    except IPControlError as err:
        LOGGER.debug("IP control pairing failed for %s: %r", host, err)
        return None


class SamsungTVIPControl:
    """The IP control API of a Samsung TV."""

    def __init__(self, hass: HomeAssistant, entry: SamsungTVConfigEntry) -> None:
        """Initialize the IP control API."""
        self._hass = hass
        self._entry = entry
        self._host: str = entry.data[CONF_HOST]
        self._client = _async_get_client(
            hass, self._host, entry.data[CONF_IP_CONTROL_TOKEN]
        )
        self._available = True
        self.auth_failed = False
        self.states: dict[str, Any] = {}

    @property
    def source(self) -> str | None:
        """Return the selected input source."""
        return self.states.get(KEY_INPUT_SOURCE)

    def _handle_auth_failed(self) -> None:
        """Start a reauth flow as the access token is no longer accepted."""
        if self.auth_failed:
            return
        self.auth_failed = True
        self.states = {}
        LOGGER.warning(
            "The IP control access token of %s is no longer valid", self._host
        )
        self._entry.async_start_reauth(self._hass, data={REAUTH_IP_CONTROL: True})

    async def async_update(self) -> None:
        """Update the states of the TV."""
        if self.auth_failed:
            return
        try:
            self.states = await self._client.get_tv_states()
        except IPControlUnauthorizedError:
            self._handle_auth_failed()
        except IPControlError as err:
            self.states = {}
            if self._available:
                LOGGER.info("IP control of %s is unavailable: %r", self._host, err)
                self._available = False
        else:
            if not self._available:
                LOGGER.info("IP control of %s is available again", self._host)
                self._available = True

    def _command_error(self, err: IPControlError) -> HomeAssistantError:
        """Return the error to raise when a command fails."""
        if isinstance(err, IPControlUnauthorizedError):
            self._handle_auth_failed()
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="error_sending_command",
            translation_placeholders={"host": self._host, "error": repr(err)},
        )

    async def async_power_on(self) -> None:
        """Turn on the TV."""
        try:
            await self._client.power_on()
        except IPControlResponseError as err:
            if err.code != ERROR_FAILED:
                raise self._command_error(err) from err
            # Some models report a failure in standby while still turning on
            LOGGER.debug("Ignoring power on failure of %s: %r", self._host, err)
        except IPControlError as err:
            raise self._command_error(err) from err

    async def async_select_source(self, source: str) -> None:
        """Select an input source."""
        try:
            await self._client.input_source_control(source)
        except IPControlError as err:
            raise self._command_error(err) from err
        self.states[KEY_INPUT_SOURCE] = source
