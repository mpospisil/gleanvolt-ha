"""Request bodies for starting a mode and quoting a plan, in the API's own shape.

Shared by the Charge mode select (which reads the held parameters) and the service actions (which
take their own fields), so both send exactly the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import MODES_REVERSED, PRIORITIES_REVERSED


@dataclass
class Drafts:
    """The parameters held in Home Assistant for the next start. Not a controller setting."""

    fast_basis: str = "full"
    fast_energy_kwh: float | None = None
    fast_target_soc: float | None = None
    fast_depart_by: datetime | None = None
    target_basis: str = "energy"
    target_energy_kwh: float | None = None
    target_soc: float | None = None
    depart_by: datetime | None = None
    priority: str = "cheapest"
    rest_soc: float | None = None
    sun_only: bool = False
    low_tariff_only: bool = False


def _timestamp(value: datetime) -> str:
    """ISO-8601 with an offset: a departure is a local-time promise."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return value.isoformat()


def fast_body(
    basis: str | None,
    energy_kwh: float | None,
    target_soc: float | None,
    depart_by: datetime | None,
) -> dict[str, Any] | None:
    """``fast`` for ``fastNoBattery``. None means "until the car says stop" (``full``, now)."""
    basis = basis or "full"
    body: dict[str, Any] = {"basis": basis}
    if basis == "energy" and energy_kwh is not None:
        body["energyWh"] = round(energy_kwh * 1000)
    if basis == "soc" and target_soc is not None:
        body["targetSocPercent"] = target_soc
    if depart_by is not None:
        body["departBy"] = _timestamp(depart_by)
    if body == {"basis": "full"}:
        return None
    return body


def target_body(
    basis: str | None,
    energy_kwh: float | None,
    target_soc: float | None,
    depart_by: datetime | None,
    priority: str | None,
    rest_soc: float | None,
    sun_only: bool,
    low_tariff_only: bool,
) -> dict[str, Any]:
    """``target`` for ``targeted``, and the preview's body.

    What is missing is left out rather than guessed at, so the controller says what it needs.
    """
    body: dict[str, Any] = {}
    if basis == "soc" or (basis is None and energy_kwh is None):
        if target_soc is not None:
            body["targetSocPercent"] = target_soc
    elif energy_kwh is not None:
        body["energyWh"] = round(energy_kwh * 1000)
    if depart_by is not None:
        body["departBy"] = _timestamp(depart_by)
    body["priority"] = PRIORITIES_REVERSED.get(priority or "cheapest", "cheapest")
    if rest_soc is not None and body["priority"] == "justInTime":
        body["restSocPercent"] = rest_soc
    editable: dict[str, Any] = {}
    if sun_only:
        editable["maxGridEnergyWh"] = 0
    if low_tariff_only:
        editable["lowTariffOnly"] = True
    if editable:
        body["editable"] = editable
    return body


def start_body(
    mode: str, *, fast: dict[str, Any] | None = None, target: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``POST /charging/start``. ``mode`` is Home Assistant's snake-cased option."""
    api_mode = MODES_REVERSED[mode]
    body: dict[str, Any] = {"mode": api_mode}
    if api_mode == "fastNoBattery" and fast is not None:
        body["fast"] = fast
    if api_mode == "targeted":
        body["target"] = target or {}
    return body


def start_from_drafts(mode: str, drafts: Drafts, now: datetime) -> dict[str, Any]:
    """The Charge mode select's start: the mode plus what that mode needs from the held entities."""
    if mode == "fast_no_battery":
        depart = drafts.fast_depart_by
        # The datetime entity cannot be emptied, so a departure already past means "now".
        if depart is not None and depart <= now:
            depart = None
        return start_body(
            mode,
            fast=fast_body(
                drafts.fast_basis, drafts.fast_energy_kwh, drafts.fast_target_soc, depart
            ),
        )
    if mode == "targeted":
        return start_body(
            mode,
            target=target_body(
                drafts.target_basis,
                drafts.target_energy_kwh,
                drafts.target_soc,
                drafts.depart_by,
                drafts.priority,
                drafts.rest_soc,
                drafts.sun_only,
                drafts.low_tariff_only,
            ),
        )
    return start_body(mode)
