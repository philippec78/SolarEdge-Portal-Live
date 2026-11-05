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
from .const import (
    CONF_NIGHT_POLL_MINUTES,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    CONF_SITE_ID,
    DEFAULT_NIGHT_POLL_MINUTES,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .readings import MAX_SAMPLE_AGE, Readings, parse_readings

_LOGGER = logging.getLogger(__name__)
_PLATFORMS = [Platform.SENSOR]
_MIN_NIGHT_SAMPLE_AGE = timedelta(minutes=5)


class PortalCoordinator(DataUpdateCoordinator[Readings]):
    """Poll once for all entities and persist refresh token changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._day_interval = timedelta(
            seconds=entry.options.get(
                CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            )
        )
        self._night_interval = timedelta(
            minutes=entry.options.get(CONF_NIGHT_POLL_MINUTES, DEFAULT_NIGHT_POLL_MINUTES)
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

    def _poll_timing(self) -> tuple[timedelta, float, bool]:
        """Choose the cadence and sample age limit for the current solar period."""
        now = datetime.now(UTC)
        try:
            sunrise = get_astral_event_next(self.hass, SUN_EVENT_SUNRISE, now)
            sunset = get_astral_event_next(self.hass, SUN_EVENT_SUNSET, now)
        except ValueError:
            return self._day_interval, MAX_SAMPLE_AGE, True

        daytime = sunset < sunrise
        interval = self._day_interval if daytime else self._night_interval
        max_age = MAX_SAMPLE_AGE
        if not daytime:
            max_age = max(
                _MIN_NIGHT_SAMPLE_AGE.total_seconds(),
                self._night_interval.total_seconds() + MAX_SAMPLE_AGE,
            )
        # The coordinator can round down by a fraction of a second.
        after_transition = min(sunrise, sunset) - now + timedelta(seconds=1)
        return min(interval, after_transition), max_age, daytime

    async def _async_update_data(self) -> Readings:
        original_data = self._entry.data
        try:
            data = await self._client.power_flow()
            _, max_age, daytime = self._poll_timing()
            return parse_readings(
                data, max_age_seconds=max_age, require_real_time=daytime
            )
        except LoginRequired as err:
            raise ConfigEntryAuthFailed(str(err)) from None
        except TemporaryError as err:
            interval, _, _ = self._poll_timing()
            retry_after = max(err.retry_after, interval.total_seconds())
            raise UpdateFailed(str(err), retry_after=retry_after) from None
        except PortalError as err:
            raise UpdateFailed(str(err)) from None
        finally:
            self.update_interval, _, _ = self._poll_timing()
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
