"""Integracja MPWiK Wrocław (eBOK) - godzinowe zużycie wody."""

from __future__ import annotations

from aiohttp import CookieJar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import MpwikClient
from .const import CONF_COOKIE
from .coordinator import MpwikCoordinator

PLATFORMS = [Platform.SENSOR]

type MpwikConfigEntry = ConfigEntry[MpwikCoordinator]


def create_client(hass: HomeAssistant, cookie: str) -> MpwikClient:
    """Klient z własnym słoikiem ciasteczek (sesja eBOK nie może być współdzielona)."""
    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    return MpwikClient(session, cookie)


async def async_setup_entry(hass: HomeAssistant, entry: MpwikConfigEntry) -> bool:
    client = create_client(hass, entry.data[CONF_COOKIE])
    coordinator = MpwikCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MpwikConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
