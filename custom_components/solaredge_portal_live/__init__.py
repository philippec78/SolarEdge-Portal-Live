"""Home Assistant integration for live SolarEdge portal measurements."""

from datetime import UTC, datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.sun import get_astral_event_next
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LoginRequired, PortalClient, PortalError, TemporaryError
from .const import CONF_POLL_INTERVAL, CONF_REFRESH_TOKEN, CONF_SITE_ID, DEFAULT_POLL_INTERVAL, DOMAIN
from .readings import Readings, parse_readings

_LOGGER = logging.getLogger(__name__)
_PLATFORMS = [Platform.SENSOR]
_NIGHT_INTERVAL = timedelta(minutes=15)


class PortalCoordinator(DataUpdateCoordinator[Readings]):
    """Poll once for all entities and persist refresh token changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._day_interval = timedelta(
            seconds=entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry,
            update_interval=self._day_interval,
            always_update=False,
        )
        self._entry = entry
        self._client = PortalClient(
            async_get_clientsession(hass), entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD], entry.data[CONF_SITE_ID], entry.data.get(CONF_REFRESH_TOKEN),
        )

    def _next_poll_interval(self) -> timedelta:
        now = datetime.now(UTC)
        try:
            sunrise = get_astral_event_next(self.hass, SUN_EVENT_SUNRISE, now)
            sunset = get_astral_event_next(self.hass, SUN_EVENT_SUNSET, now)
        except ValueError:
            return self._day_interval

        interval = self._day_interval if sunset < sunrise else _NIGHT_INTERVAL
        # The coordinator can round down by a fraction of a second.
        after_transition = min(sunrise, sunset) - now + timedelta(seconds=1)
        return min(interval, after_transition)

    async def _async_update_data(self) -> Readings:
        original_data = self._entry.data
        try:
            return parse_readings(await self._client.power_flow())
        except LoginRequired as err:
            raise ConfigEntryAuthFailed(str(err)) from None
        except TemporaryError as err:
            retry_after = max(err.retry_after, self._next_poll_interval().total_seconds())
            raise UpdateFailed(str(err), retry_after=retry_after) from None
        except PortalError as err:
            raise UpdateFailed(str(err)) from None
        finally:
            self.update_interval = self._next_poll_interval()
            token = self._client.refresh_token
            if self._entry.data is original_data and token != original_data.get(CONF_REFRESH_TOKEN):
                data = dict(original_data)
                data.pop(CONF_REFRESH_TOKEN, None)
                if token:
                    data[CONF_REFRESH_TOKEN] = token
                self.hass.config_entries.async_update_entry(self._entry, data=data)


type PortalEntry = ConfigEntry[PortalCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PortalEntry) -> bool:
    coordinator = PortalCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PortalEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
