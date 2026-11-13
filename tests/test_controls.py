"""The controls: what each one sends, and the controller's refusals reaching the user."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import DOMAIN as BUTTON, SERVICE_PRESS
from homeassistant.components.datetime import DOMAIN as DATETIME, SERVICE_SET_VALUE as SET_DATETIME
from homeassistant.components.number import DOMAIN as NUMBER, SERVICE_SET_VALUE
from homeassistant.components.select import DOMAIN as SELECT, SERVICE_SELECT_OPTION
from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import BASE, STATUS, action

MODE = "select.home_roof_charge_mode"


def _sent(aioclient_mock: AiohttpClientMocker, method: str, path: str) -> list[Any]:
    url = f"{BASE}{path}"
    return [
        call[2] for call in aioclient_mock.mock_calls if call[0] == method and str(call[1]) == url
    ]


async def _select(hass: HomeAssistant, entity: str, option: str) -> None:
    await hass.services.async_call(
        SELECT, SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: entity, "option": option}, blocking=True
    )


async def test_select_solar_starts_it(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/charging/start", json=action(status={**STATUS, "mode": "solar"}))
    await _select(hass, MODE, "solar")
    assert _sent(aioclient_mock, "POST", "/charging/start") == [{"mode": "solar"}]
    # The status the action answered with is shown at once.
    assert hass.states.get(MODE).state == "solar"
    assert hass.states.get("sensor.home_roof_charge_mode").state == "solar"


async def test_select_off_stops(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/charging/stop", json=action(status=STATUS))
    await _select(hass, MODE, "off")
    assert len(_sent(aioclient_mock, "POST", "/charging/stop")) == 1
    assert not _sent(aioclient_mock, "POST", "/charging/start")


async def test_select_targeted_sends_the_held_parameters(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await hass.services.async_call(
        NUMBER,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.home_roof_target_energy", "value": 22},
        blocking=True,
    )
    await hass.services.async_call(
        DATETIME,
        SET_DATETIME,
        {ATTR_ENTITY_ID: "datetime.home_roof_departure", "datetime": "2030-01-02T07:00:00+01:00"},
        blocking=True,
    )
    await _select(hass, "select.home_roof_charge_priority", "just_in_time")
    await hass.services.async_call(
        SWITCH, SERVICE_TURN_ON, {ATTR_ENTITY_ID: "switch.home_roof_target_sun_only"}, blocking=True
    )
    aioclient_mock.post(
        f"{BASE}/charging/start", json=action(status={**STATUS, "mode": "targeted"})
    )

    await _select(hass, MODE, "targeted")

    [body] = _sent(aioclient_mock, "POST", "/charging/start")
    assert body["mode"] == "targeted"
    target = body["target"]
    assert target["energyWh"] == 22000
    assert target["priority"] == "justInTime"
    assert target["editable"] == {"maxGridEnergyWh": 0}
    assert target["departBy"].startswith("2030-01-02T07:00:00")


async def test_select_fast_soc(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _select(hass, "select.home_roof_fast_basis", "soc")
    await hass.services.async_call(
        NUMBER,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.home_roof_fast_target_soc", "value": 60},
        blocking=True,
    )
    aioclient_mock.post(f"{BASE}/charging/start", json=action(status=STATUS))
    await _select(hass, MODE, "fast_no_battery")
    assert _sent(aioclient_mock, "POST", "/charging/start") == [
        {"mode": "fastNoBattery", "fast": {"basis": "soc", "targetSocPercent": 60}}
    ]


async def test_refused_400_reaches_the_user(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    reason = "The departure is in the past."
    aioclient_mock.post(
        f"{BASE}/charging/start", status=400, json={"title": "Bad request", "detail": reason}
    )
    with pytest.raises(HomeAssistantError) as raised:
        await _select(hass, MODE, "targeted")
    assert raised.value.translation_key == "refused"
    assert raised.value.translation_placeholders == {"message": reason}
    # Nothing started: the select still shows the real mode.
    assert hass.states.get(MODE).state == "off"


async def test_succeeded_false_reaches_the_user(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE}/charging/start",
        json=action(succeeded=False, message="The charger refused use-mode Fast.", status=STATUS),
    )
    with pytest.raises(HomeAssistantError) as raised:
        await _select(hass, MODE, "solar")
    assert raised.value.translation_placeholders == {
        "message": "The charger refused use-mode Fast."
    }
    assert hass.states.get(MODE).state == "off"


async def test_stop_button(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/charging/stop", json=action(status=STATUS))
    await hass.services.async_call(
        BUTTON, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.home_roof_stop_charging"}, blocking=True
    )
    assert len(_sent(aioclient_mock, "POST", "/charging/stop")) == 1


async def test_battery_hold(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    held = {**STATUS, "batteryHold": {**STATUS["batteryHold"], "requested": True, "active": True}}
    aioclient_mock.put(f"{BASE}/battery-hold", json=action(status=held))
    await hass.services.async_call(
        SWITCH,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.home_roof_battery_discharge_hold"},
        blocking=True,
    )
    assert _sent(aioclient_mock, "PUT", "/battery-hold") == [{"hold": True}]
    assert hass.states.get("switch.home_roof_battery_discharge_hold").state == "on"


async def test_battery_hold_409(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.put(
        f"{BASE}/battery-hold",
        status=409,
        json={"detail": "The battery hold is disabled (BatteryHold:Enabled is false)."},
    )
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            SWITCH,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "switch.home_roof_battery_discharge_hold"},
            blocking=True,
        )
    assert "disabled" in raised.value.translation_placeholders["message"]


async def test_battery_hold_unavailable_when_disabled(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    disabled = {**STATUS, "batteryHold": {**STATUS["batteryHold"], "enabled": False}}
    loaded_entry.runtime_data.status.async_set_updated_data(disabled)
    await hass.async_block_till_done()
    assert hass.states.get("switch.home_roof_battery_discharge_hold").state == "unavailable"


async def test_low_tariff_only_sends_one_field(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.put(
        f"{BASE}/charging/low-tariff-only",
        json={"fastNoBattery": True, "solarGrid": True, "tariffKnown": True},
    )
    await hass.services.async_call(
        SWITCH,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.home_roof_fast_low_tariff_only"},
        blocking=True,
    )
    assert _sent(aioclient_mock, "PUT", "/charging/low-tariff-only") == [{"fastNoBattery": True}]
    assert hass.states.get("switch.home_roof_fast_low_tariff_only").state == "on"


async def test_until_full(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.put(f"{BASE}/charging/until-full", json={"untilFull": True, "session": None})
    await hass.services.async_call(
        SWITCH,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.home_roof_forecasted_until_full"},
        blocking=True,
    )
    assert _sent(aioclient_mock, "PUT", "/charging/until-full") == [{"untilFull": True}]
    assert hass.states.get("switch.home_roof_forecasted_until_full").state == "on"


async def test_held_entities_are_not_sent_until_a_start(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    before = len(aioclient_mock.mock_calls)
    await hass.services.async_call(
        NUMBER,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.home_roof_fast_energy", "value": 10},
        blocking=True,
    )
    await _select(hass, "select.home_roof_target_basis", "soc")
    assert len(aioclient_mock.mock_calls) == before
    assert hass.states.get("number.home_roof_fast_energy").state == "10.0"


async def test_mode_to_start_then_start(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Like a web UI tab: picking the mode sends nothing; Start starts it with that tab's values."""
    before = len(aioclient_mock.mock_calls)
    await _select(hass, "select.home_roof_mode_to_start", "fast_no_battery")
    await _select(hass, "select.home_roof_fast_basis", "energy")
    await hass.services.async_call(
        NUMBER,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.home_roof_fast_energy", "value": 12},
        blocking=True,
    )
    assert len(aioclient_mock.mock_calls) == before
    assert hass.states.get(MODE).state == "off"

    aioclient_mock.post(
        f"{BASE}/charging/start", json=action(status={**STATUS, "mode": "fastNoBattery"})
    )
    await hass.services.async_call(
        BUTTON, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.home_roof_start"}, blocking=True
    )
    assert _sent(aioclient_mock, "POST", "/charging/start") == [
        {"mode": "fastNoBattery", "fast": {"basis": "energy", "energyWh": 12000}}
    ]
    assert hass.states.get(MODE).state == "fast_no_battery"


async def test_start_refused_reaches_the_user(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _select(hass, "select.home_roof_mode_to_start", "targeted")
    aioclient_mock.post(
        f"{BASE}/charging/start", status=400, json={"detail": "Set a departure first."}
    )
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            BUTTON, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.home_roof_start"}, blocking=True
        )
    assert raised.value.translation_placeholders == {"message": "Set a departure first."}
