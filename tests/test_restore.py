"""The held parameters come back after a Home Assistant restart, and are what the next start sends."""

from __future__ import annotations

from homeassistant.components.select import DOMAIN as SELECT, SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import BASE, STATUS, action, mock_api


async def test_restored_drafts_are_sent(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    # One cache: a second mock_restore_cache* call replaces the first.
    mock_restore_cache_with_extra_data(
        hass,
        [
            (State("select.home_roof_target_basis", "soc"), {}),
            (State("datetime.home_roof_departure", "2030-01-02T06:00:00+00:00"), {}),
            (State("switch.home_roof_target_low_tariff_only", "on"), {}),
            (
                State("number.home_roof_target_soc", "80"),
                {
                    "native_value": 80.0,
                    "native_unit_of_measurement": "%",
                    "native_min_value": 1,
                    "native_max_value": 100,
                    "native_step": 1,
                },
            ),
        ],
    )
    mock_api(aioclient_mock)
    aioclient_mock.post(f"{BASE}/charging/start", json=action(status=STATUS))
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("select.home_roof_target_basis").state == "soc"
    assert hass.states.get("number.home_roof_target_soc").state == "80.0"
    assert hass.states.get("switch.home_roof_target_low_tariff_only").state == "on"

    await hass.services.async_call(
        SELECT,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.home_roof_charge_mode", "option": "targeted"},
        blocking=True,
    )
    [body] = [c[2] for c in aioclient_mock.mock_calls if str(c[1]).endswith("/charging/start")]
    assert body == {
        "mode": "targeted",
        "target": {
            "targetSocPercent": 80.0,
            "departBy": "2030-01-02T06:00:00+00:00",
            "priority": "cheapest",
            "editable": {"lowTariffOnly": True},
        },
    }
