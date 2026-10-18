"""Konfiguracja integracji MPWiK Wrocław przez interfejs."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from . import create_client
from .api import MpwikAuthError, MpwikError
from .const import (
    CONF_ADRES,
    CONF_BACKFILL_DAYS,
    CONF_COOKIE,
    CONF_PODMIOT,
    CONF_PUNKT,
    DEFAULT_BACKFILL_DAYS,
    DOMAIN,
    MAX_BACKFILL_DAYS,
)

_LOGGER = logging.getLogger(__name__)

_COOKIE_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))


class MpwikConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._punkty: list[dict[str, Any]] = []

    async def _validate(self, cookie: str, podmiot: str) -> tuple[dict[str, str], list]:
        errors: dict[str, str] = {}
        punkty: list[dict[str, Any]] = []
        client = create_client(self.hass, cookie)
        try:
            await client.session_info()
            punkty = await client.punkty_sieci(podmiot)
            if not punkty:
                errors["base"] = "no_points"
        except MpwikAuthError:
            errors["base"] = "invalid_auth"
        except MpwikError:
            _LOGGER.exception("Błąd połączenia z eBOK")
            errors["base"] = "cannot_connect"
        return errors, punkty

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_PODMIOT] = user_input[CONF_PODMIOT].strip()
            errors, self._punkty = await self._validate(
                user_input[CONF_COOKIE], user_input[CONF_PODMIOT]
            )
            if not errors:
                self._user_input = user_input
                return await self.async_step_punkt()

        schema = vol.Schema(
            {
                vol.Required(CONF_PODMIOT): str,
                vol.Required(CONF_COOKIE): _COOKIE_SELECTOR,
                vol.Required(CONF_BACKFILL_DAYS, default=DEFAULT_BACKFILL_DAYS): NumberSelector(
                    NumberSelectorConfig(min=1, max=MAX_BACKFILL_DAYS, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_punkt(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            punkt = next(p for p in self._punkty if p["numer"] == user_input[CONF_PUNKT])
            podmiot = self._user_input[CONF_PODMIOT]
            await self.async_set_unique_id(f"{podmiot}_{punkt['numer']}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=punkt["adres"],
                data={
                    CONF_PODMIOT: podmiot,
                    CONF_COOKIE: self._user_input[CONF_COOKIE].strip(),
                    CONF_BACKFILL_DAYS: int(self._user_input[CONF_BACKFILL_DAYS]),
                    CONF_PUNKT: punkt["numer"],
                    CONF_ADRES: punkt["adres"],
                },
            )

        options = [
            SelectOptionDict(value=p["numer"], label=f"{p['numer']} - {p['adres']}")
            for p in self._punkty
        ]
        return self.async_show_form(
            step_id="punkt",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PUNKT, default=options[0]["value"]): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, _ = await self._validate(user_input[CONF_COOKIE], entry.data[CONF_PODMIOT])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_COOKIE: user_input[CONF_COOKIE].strip()}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): _COOKIE_SELECTOR}),
            errors=errors,
        )
