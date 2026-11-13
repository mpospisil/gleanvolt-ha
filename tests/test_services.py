"""The service actions."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.gleanvolt.const import DOMAIN

from .conftest import BASE, STATUS, action

PLAN = {"strategy": "solarPlusGrid", "gridEnergyWh": 8000, "reason": "Grid from 02:00."}


def _bodies(aioclient_mock: AiohttpClientMocker, path: str) -> list:
    return [call[2] for call in aioclient_mock.mock_calls if str(call[1]) == f"{BASE}{path}"]


async def test_start_targeted(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE}/charging/start", json=action(status={**STATUS, "mode": "targeted"})
    )
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {
            "mode": "targeted",
            "target_soc": 80,
            "depart_by": "2030-01-02T07:00:00+01:00",
            "low_tariff_only": True,
        },
        blocking=True,
    )
    [body] = _bodies(aioclient_mock, "/charging/start")
    assert body["mode"] == "targeted"
    assert body["target"]["targetSocPercent"] == 80
    assert body["target"]["editable"] == {"lowTariffOnly": True}
    assert body["target"]["departBy"].startswith("2030-01-02T07:00:00")
    assert hass.states.get("select.home_roof_charge_mode").state == "targeted"


async def test_start_fast_energy(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/charging/start", json=action(status=STATUS))
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {"mode": "fast_no_battery", "basis": "energy", "energy_kwh": 15},
        blocking=True,
    )
    assert _bodies(aioclient_mock, "/charging/start") == [
        {"mode": "fastNoBattery", "fast": {"basis": "energy", "energyWh": 15000}}
    ]


async def test_start_refused(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE}/charging/start", status=400, json={"detail": "No reading from the car."}
    )
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            DOMAIN,
            "start_charging",
            {"mode": "targeted", "target_soc": 80, "depart_by": "2030-01-02T07:00:00+01:00"},
            blocking=True,
        )
    assert raised.value.translation_placeholders == {"message": "No reading from the car."}


async def test_stop(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/charging/stop", json=action(status=STATUS))
    await hass.services.async_call(DOMAIN, "stop_charging", {}, blocking=True)
    assert len(_bodies(aioclient_mock, "/charging/stop")) == 1


async def test_preview_returns_the_plan_and_starts_nothing(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    preview = {"request": {}, "plan": PLAN, "cheapestPlan": None, "editable": {"planId": "x"}}
    aioclient_mock.post(f"{BASE}/plans/targeted/preview", json=preview)
    response = await hass.services.async_call(
        DOMAIN,
        "preview_targeted",
        {"target_soc": 80, "depart_by": "2030-01-02T07:00:00+01:00", "sun_only": True},
        blocking=True,
        return_response=True,
    )
    assert response == preview
    [body] = _bodies(aioclient_mock, "/plans/targeted/preview")
    assert body["targetSocPercent"] == 80
    assert body["editable"] == {"maxGridEnergyWh": 0}
    assert not _bodies(aioclient_mock, "/charging/start")
    assert hass.states.get("select.home_roof_charge_mode").state == "off"


async def test_unknown_entry(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "stop_charging", {"config_entry_id": "nope"}, blocking=True
        )
