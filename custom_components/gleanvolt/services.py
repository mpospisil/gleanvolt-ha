"""Service actions: start, stop and quote, with their own fields, so no automation depends on held state."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .api import GleanvoltError
from .const import DOMAIN, FAST_BASES, MODES, PRIORITIES
from .data import GleanvoltConfigEntry
from .entity import controller_error
from .payload import fast_body, start_body, target_body

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_MODE = "mode"
ATTR_BASIS = "basis"
ATTR_ENERGY_KWH = "energy_kwh"
ATTR_TARGET_SOC = "target_soc"
ATTR_DEPART_BY = "depart_by"
ATTR_PRIORITY = "priority"
ATTR_REST_SOC = "rest_soc"
ATTR_SUN_ONLY = "sun_only"
ATTR_LOW_TARIFF_ONLY = "low_tariff_only"

SERVICE_START = "start_charging"
SERVICE_STOP = "stop_charging"
SERVICE_PREVIEW = "preview_targeted"

_ENTRY = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
_SOC = vol.All(vol.Coerce(float), vol.Range(min=0, max=100))
_KWH = vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))
_TARGETED = {
    vol.Optional(ATTR_ENERGY_KWH): _KWH,
    vol.Optional(ATTR_TARGET_SOC): _SOC,
    vol.Optional(ATTR_DEPART_BY): cv.datetime,
    vol.Optional(ATTR_PRIORITY): vol.In(list(PRIORITIES.values())),
    vol.Optional(ATTR_REST_SOC): _SOC,
    vol.Optional(ATTR_SUN_ONLY, default=False): cv.boolean,
    vol.Optional(ATTR_LOW_TARIFF_ONLY, default=False): cv.boolean,
}

START_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        vol.Required(ATTR_MODE): vol.In([mode for mode in MODES.values() if mode != "off"]),
        vol.Optional(ATTR_BASIS): vol.In(list(FAST_BASES)),
        **_TARGETED,
    }
)
STOP_SCHEMA = vol.Schema(_ENTRY)
PREVIEW_SCHEMA = vol.Schema({**_ENTRY, **_TARGETED})


def _entry(hass: HomeAssistant, call: ServiceCall) -> GleanvoltConfigEntry:
    """The installation named, or the only one there is."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if wanted is not None:
        entries = [entry for entry in entries if entry.entry_id == wanted]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entry": wanted},
            )
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_single_entry" if entries else "no_entry",
        )
    return entries[0]


def _target(data: dict[str, Any]) -> dict[str, Any]:
    return target_body(
        None,
        data.get(ATTR_ENERGY_KWH),
        data.get(ATTR_TARGET_SOC),
        data.get(ATTR_DEPART_BY),
        data.get(ATTR_PRIORITY),
        data.get(ATTR_REST_SOC),
        data[ATTR_SUN_ONLY],
        data[ATTR_LOW_TARIFF_ONLY],
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def start(call: ServiceCall) -> None:
        entry = _entry(hass, call)
        mode = call.data[ATTR_MODE]
        if mode == "fast_no_battery":
            body = start_body(
                mode,
                fast=fast_body(
                    call.data.get(ATTR_BASIS),
                    call.data.get(ATTR_ENERGY_KWH),
                    call.data.get(ATTR_TARGET_SOC),
                    call.data.get(ATTR_DEPART_BY),
                ),
            )
        elif mode == "targeted":
            body = start_body(mode, target=_target(call.data))
        else:
            body = start_body(mode)
        try:
            result = await entry.runtime_data.client.start(body)
        except GleanvoltError as err:
            raise controller_error(err) from err
        entry.runtime_data.apply_action(result)

    async def stop(call: ServiceCall) -> None:
        entry = _entry(hass, call)
        try:
            result = await entry.runtime_data.client.stop()
        except GleanvoltError as err:
            raise controller_error(err) from err
        entry.runtime_data.apply_action(result)

    async def preview(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        try:
            return await entry.runtime_data.client.preview_targeted(_target(call.data))
        except GleanvoltError as err:
            raise controller_error(err) from err

    hass.services.async_register(DOMAIN, SERVICE_START, start, schema=START_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, stop, schema=STOP_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIEW,
        preview,
        schema=PREVIEW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
