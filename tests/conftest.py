"""Fixtures: a Gleanvolt 1.2.0 answering on 192.168.1.20:8090, mocked at the HTTP layer."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.gleanvolt.const import DOMAIN

HOST = "192.168.1.20"
PORT = 8090
KEY = "secret-key"
BASE = f"http://{HOST}:{PORT}/api/v1"
SYSTEM_ID = "home-roof"

HEALTH: dict[str, Any] = {
    "ok": True,
    "version": "1.2.0 (31bf347)",
    "systemId": SYSTEM_ID,
    "systemName": "Home roof",
    "now": "2026-11-13T10:00:00+01:00",
    "timeZoneId": "Europe/Prague",
    "lastPollAt": "2026-11-13T09:59:58+01:00",
    "lastPollAgeSeconds": 2.1,
    "mode": "off",
    "dryRun": False,
    "forecastAvailable": True,
    "forecastRetrievedAt": "2026-11-13T06:00:00+01:00",
    "weatherConfigured": False,
    "vehicleAvailable": True,
    "vehicleAgeSeconds": 600,
    "vehicleStale": False,
    "energyHistoryAvailable": True,
    "sessionHistoryAvailable": True,
    "secretStore": "owner-only files (0600) in the data directory",
}

STATUS: dict[str, Any] = {
    "timestamp": "2026-11-13T10:00:00+01:00",
    "mode": "off",
    "state": "disabled",
    "dryRun": False,
    "holdingControl": False,
    "solarPowerWatts": 3200.0,
    "forecastSolarPowerWatts": 2900.0,
    "gridPowerWatts": -1200.0,
    "batteryPowerWatts": 1500.0,
    "batterySocPercent": 64.0,
    "evChargerPowerWatts": 0.0,
    "evChargingCurrentAmps": 0,
    "targetCurrentAmps": None,
    "activeCurrentAmps": 6,
    "surplusWatts": None,
    "chargerStatus": "suspendedEvse",
    "carConnected": True,
    "sessionEnergyWh": 4321.0,
    "loanPowerWatts": 0.0,
    "loanedTodayWh": 0.0,
    "tomorrowForecastWh": 18400.0,
    "batteryHold": {"enabled": True, "requested": False, "active": False, "targetWatts": None},
    "dayPlan": None,
    "targetedPlan": None,
    "fastCharge": None,
    "lowTariff": None,
    "untilFull": None,
}

VEHICLE: dict[str, Any] = {
    "available": True,
    "capturedAt": "2026-11-13T09:50:00+01:00",
    "ageSeconds": 600,
    "stale": False,
    "socPercent": 41.0,
    "rangeMetres": 152000.0,
    "chargeTimeRemainingSeconds": None,
    "chargeState": "idle",
    "plugState": "connected",
    "sourceId": "skoda",
    "canTargetSoc": True,
    "vehicle": None,
}

TARIFF: dict[str, Any] = {
    "provider": "Table",
    "providerName": "Table",
    "currency": "CZK",
    "unavailable": None,
    "now": {"rate": "low", "pricePerKwh": 2.5, "until": "2026-11-13T12:00:00+01:00"},
    "windows": [],
    "lowPricePerKwh": 2.5,
    "highPricePerKwh": 5.0,
}

LOW_TARIFF_ONLY = {"fastNoBattery": False, "solarGrid": True, "tariffKnown": True}
UNTIL_FULL = {"untilFull": False, "session": None}
FORECAST: dict[str, Any] = {
    "retrievedAt": "2026-11-13T06:00:00+01:00",
    "days": [],
    "todayExpectedWh": 12400.0,
    "todayRemainingWh": 5100.0,
    "tomorrowExpectedWh": 18400.0,
    "peakPowerWatts": 3900.0,
    "periods": [],
    "weather": None,
}


def action(succeeded: bool = True, message: str | None = None, status: dict | None = None) -> dict:
    return {
        "succeeded": succeeded,
        "message": message,
        "target": None,
        "status": status,
        "fast": None,
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture
def status() -> dict[str, Any]:
    return copy.deepcopy(STATUS)


def mock_api(
    aioclient_mock: AiohttpClientMocker,
    *,
    status: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
) -> None:
    """Every GET the integration makes, answering as a healthy 1.2.0."""
    aioclient_mock.get(f"{BASE}/health", json=health or HEALTH)
    aioclient_mock.get(f"{BASE}/status", json=status or STATUS)
    aioclient_mock.get(f"{BASE}/vehicle", json=VEHICLE)
    aioclient_mock.get(f"{BASE}/tariff", json=TARIFF)
    aioclient_mock.get(f"{BASE}/charging/low-tariff-only", json=LOW_TARIFF_ONLY)
    aioclient_mock.get(f"{BASE}/charging/until-full", json=UNTIL_FULL)
    aioclient_mock.get(f"{BASE}/forecast", json=FORECAST)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Home roof",
        unique_id=SYSTEM_ID,
        data={CONF_HOST: HOST, CONF_PORT: PORT, CONF_API_KEY: KEY},
    )


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    mock_api(aioclient_mock)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
