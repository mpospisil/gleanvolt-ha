"""Setup: zeroconf or by hand, one API key; reauth, reconfigure and the poll interval."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api import (
    GleanvoltApiDisabledError,
    GleanvoltAuthError,
    GleanvoltClient,
    GleanvoltConnectionError,
    GleanvoltError,
    parse_version,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_VERSION,
    MIN_VERSION_TEXT,
)

_KEY = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_PORT = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))


class UnsupportedVersion(Exception):
    def __init__(self, version: str) -> None:
        super().__init__(version)
        self.version = version


async def _validate(flow: ConfigFlow, host: str, port: int, api_key: str) -> dict[str, Any]:
    """``GET /health`` with the key: who is answering, and is it new enough."""
    client = GleanvoltClient(async_get_clientsession(flow.hass), host, port, api_key)
    health = await client.health()
    version = parse_version(health.get("version"))
    if version is None or version < MIN_VERSION:
        raise UnsupportedVersion(str(health.get("version")))
    return health


def _error(err: Exception) -> str:
    if isinstance(err, GleanvoltAuthError):
        return "invalid_auth"
    if isinstance(err, GleanvoltApiDisabledError):
        return "api_disabled"
    if isinstance(err, UnsupportedVersion):
        return "unsupported_version"
    if isinstance(err, GleanvoltConnectionError):
        return "cannot_connect"
    return "unknown"


class GleanvoltConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str = "Gleanvolt"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> GleanvoltOptionsFlow:
        return GleanvoltOptionsFlow()

    async def _try(
        self,
        host: str,
        port: int,
        api_key: str,
        errors: dict[str, str],
        placeholders: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            return await _validate(self, host, port, api_key)
        except (GleanvoltError, UnsupportedVersion) as err:
            errors["base"] = _error(err)
            if isinstance(err, UnsupportedVersion):
                placeholders["version"] = err.version
            return None

    async def _create(
        self, health: dict[str, Any], host: str, port: int, api_key: str
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(health["systemId"])
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
        return self.async_create_entry(
            title=health.get("systemName") or "Gleanvolt",
            data={CONF_HOST: host, CONF_PORT: port, CONF_API_KEY: api_key},
        )

    def _placeholders(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {"minimum": MIN_VERSION_TEXT, "version": "", "name": self._name, **(extra or {})}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = self._placeholders()
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            health = await self._try(host, port, user_input[CONF_API_KEY], errors, placeholders)
            if health is not None:
                return await self._create(health, host, port, user_input[CONF_API_KEY])
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(
                    CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)
                ): _PORT,
                vol.Required(CONF_API_KEY): _KEY,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors, description_placeholders=placeholders
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """``_gleanvolt._tcp``: host and port come from the announcement; only the key is asked."""
        self._host = discovery_info.host
        self._port = discovery_info.port or DEFAULT_PORT
        # The systemId needs the key, so until then an installation is known by its address: one
        # flow per address, and none for an address already set up.
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_HOST) in (self._host, discovery_info.hostname.rstrip(".")):
                return self.async_abort(reason="already_configured")
        await self.async_set_unique_id(f"{self._host}:{self._port}")
        self._abort_if_unique_id_configured()
        self._name = discovery_info.name.split(".")[0]
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        errors: dict[str, str] = {}
        placeholders = self._placeholders({"host": self._host, "port": str(self._port)})
        if user_input is not None:
            health = await self._try(
                self._host, self._port, user_input[CONF_API_KEY], errors, placeholders
            )
            if health is not None:
                return await self._create(health, self._host, self._port, user_input[CONF_API_KEY])
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _KEY}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        placeholders = self._placeholders({"name": entry.title})
        if user_input is not None:
            health = await self._try(
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                user_input[CONF_API_KEY],
                errors,
                placeholders,
            )
            if health is not None:
                await self.async_set_unique_id(health["systemId"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _KEY}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders = self._placeholders({"name": entry.title})
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            health = await self._try(host, port, entry.data[CONF_API_KEY], errors, placeholders)
            if health is not None:
                await self.async_set_unique_id(health["systemId"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host, CONF_PORT: port}
                )
        current = user_input or entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=current[CONF_PORT]): _PORT,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class GleanvoltOptionsFlow(OptionsFlow):
    """How often ``/status`` is polled."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    )
                }
            ),
        )
