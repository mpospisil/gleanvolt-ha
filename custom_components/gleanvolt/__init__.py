"""The Gleanvolt integration: one installation, over its HTTP API."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    GleanvoltApiDisabledError,
    GleanvoltAuthError,
    GleanvoltClient,
    GleanvoltError,
    parse_version,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_VERSION,
    MIN_VERSION_TEXT,
)
from .coordinator import GleanvoltSlowCoordinator, GleanvoltStatusCoordinator
from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATETIME,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Service actions are registered once, for every installation."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GleanvoltConfigEntry) -> bool:
    client = GleanvoltClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_KEY],
    )

    try:
        health = await client.health()
    except GleanvoltAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except GleanvoltApiDisabledError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="api_disabled"
        ) from err
    except GleanvoltError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    version = parse_version(health.get("version"))
    if version is None or version < MIN_VERSION:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_version",
            translation_placeholders={
                "version": str(health.get("version")),
                "minimum": MIN_VERSION_TEXT,
            },
        )

    interval = timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    status = GleanvoltStatusCoordinator(hass, entry, client, interval)
    slow = GleanvoltSlowCoordinator(hass, entry, client, health)
    await status.async_config_entry_first_refresh()
    await slow.async_config_entry_first_refresh()

    entry.runtime_data = GleanvoltRuntime(
        client=client,
        status=status,
        slow=slow,
        system_id=health["systemId"],
        system_name=health.get("systemName") or "Gleanvolt",
        version=health.get("version") or "",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: GleanvoltConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GleanvoltConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
