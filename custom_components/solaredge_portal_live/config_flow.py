"""Set up the integration with the credentials of a SolarEdge account."""

from __future__ import annotations

import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LoginRequired, PortalClient, PortalError, SiteAccessDenied
from .const import (
    CONF_NIGHT_POLL_MINUTES,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    CONF_SITE_ID,
    DEFAULT_NIGHT_POLL_MINUTES,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_INTERVAL = selector.NumberSelector(
    selector.NumberSelectorConfig(min=15, max=120, step=1, mode=selector.NumberSelectorMode.BOX)
)
_PASSWORD = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


class PortalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Validate the account and site before creating an entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> PortalOptionsFlow:
        return PortalOptionsFlow()

    async def async_step_user(self, user_input=None):
        return await self._credentials("user", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._credentials("reauth_confirm", user_input, self._get_reauth_entry())

    async def async_step_reconfigure(self, user_input=None):
        return await self._credentials("reconfigure", user_input, self._get_reconfigure_entry())

    async def _credentials(self, step, user_input, entry=None):
        errors = {}
        if user_input is not None:
            interval = user_input.get(
                CONF_POLL_INTERVAL,
                entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
                if entry else DEFAULT_POLL_INTERVAL,
            )
            data = {
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_SITE_ID: entry.data[CONF_SITE_ID] if entry else user_input[CONF_SITE_ID].strip(),
            }
            if not re.fullmatch(r"[0-9]+", data[CONF_SITE_ID]):
                errors[CONF_SITE_ID] = "invalid_site"
            elif not 15 <= interval <= 120 or interval % 1:
                errors[CONF_POLL_INTERVAL] = "invalid_interval"
            elif not data[CONF_USERNAME] or not data[CONF_PASSWORD]:
                errors["base"] = "invalid_auth"
            else:
                data[CONF_POLL_INTERVAL] = int(interval)
                await self.async_set_unique_id(data[CONF_SITE_ID])
                if not entry:
                    self._abort_if_unique_id_configured()
                client = PortalClient(
                    async_get_clientsession(self.hass), data[CONF_USERNAME],
                    data[CONF_PASSWORD], data[CONF_SITE_ID],
                )
                try:
                    await client.power_flow()
                except LoginRequired:
                    errors["base"] = "invalid_auth"
                except SiteAccessDenied:
                    errors["base"] = "invalid_site"
                except PortalError:
                    errors["base"] = "cannot_connect"
                else:
                    if client.refresh_token:
                        data[CONF_REFRESH_TOKEN] = client.refresh_token
                    if entry:
                        return self.async_update_reload_and_abort(entry, data=data)
                    return self.async_create_entry(
                        title=f"SolarEdge Live {data[CONF_SITE_ID]}", data=data
                    )

        current = entry.data if entry else {}
        fields = {vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): str,
                  vol.Required(CONF_PASSWORD): _PASSWORD}
        if not entry:
            fields[vol.Required(CONF_SITE_ID)] = str
        if step != "reauth_confirm":
            fields[vol.Required(
                CONF_POLL_INTERVAL, default=current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            )] = _INTERVAL
        return self.async_show_form(
            step_id=step, data_schema=vol.Schema(fields), errors=errors,
        )


class PortalOptionsFlow(config_entries.OptionsFlowWithReload):
    """Save the nighttime cadence without signing in again."""

    async def async_step_init(self, user_input=None):
        current = self.config_entry.options
        interval = current.get(CONF_NIGHT_POLL_MINUTES, DEFAULT_NIGHT_POLL_MINUTES)
        errors = {}
        if user_input is not None:
            interval = user_input[CONF_NIGHT_POLL_MINUTES]
            if 1 <= interval <= 120 and interval % 1 == 0:
                return self.async_create_entry(
                    title="", data={**current, CONF_NIGHT_POLL_MINUTES: int(interval)}
                )
            errors[CONF_NIGHT_POLL_MINUTES] = "invalid_night_interval"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_NIGHT_POLL_MINUTES, default=interval): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=120, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }),
            errors=errors,
        )
