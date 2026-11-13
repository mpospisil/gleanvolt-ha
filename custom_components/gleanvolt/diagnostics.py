"""Diagnostics download, with the key redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .data import GleanvoltConfigEntry

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GleanvoltConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    slow = runtime.slow.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "drafts": runtime.drafts.__dict__,
        "status": runtime.status.data,
        "health": slow.health if slow else None,
        "vehicle": slow.vehicle if slow else None,
        "tariff": slow.tariff if slow else None,
        "low_tariff_only": slow.low_tariff_only if slow else None,
        "until_full": slow.until_full if slow else None,
        "forecast": {
            key: value for key, value in (slow.forecast if slow else {}).items() if key != "periods"
        },
    }
