"""Setup, the polls, and what failure looks like."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.gleanvolt.const import DOMAIN

from .conftest import BASE, HEALTH, STATUS, SYSTEM_ID, mock_api


async def test_setup_and_device(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert loaded_entry.state is ConfigEntryState.LOADED
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, SYSTEM_ID)})
    assert device is not None
    assert device.name == "Home roof"
    assert device.sw_version == "1.2.0 (31bf347)"
    assert device.configuration_url == "http://192.168.1.20:8090"


async def test_sensors(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert hass.states.get("sensor.home_roof_battery_soc").state == "64.0"
    assert hass.states.get("sensor.home_roof_charge_mode").state == "off"
    assert hass.states.get("sensor.home_roof_charger_status").state == "suspended_evse"
    assert hass.states.get("sensor.home_roof_session_energy").state == "4.321"
    assert hass.states.get("sensor.home_roof_target_charging_current").state == "unknown"
    # Mode-specific figures are unknown outside their mode.
    assert hass.states.get("sensor.home_roof_ev_energy_budget").state == "unknown"
    assert hass.states.get("sensor.home_roof_target_grid_energy").state == "unknown"
    assert hass.states.get("sensor.home_roof_car_range").state == "152.0"
    assert hass.states.get("sensor.home_roof_forecast_today").state == "12.4"
    assert hass.states.get("sensor.home_roof_forecast_still_to_come").state == "5.1"
    price = hass.states.get("sensor.home_roof_grid_price")
    assert price.state == "2.5"
    assert price.attributes["unit_of_measurement"] == "CZK/kWh"
    assert hass.states.get("binary_sensor.home_roof_low_tariff").state == "on"
    assert hass.states.get("binary_sensor.home_roof_car_connected").state == "on"
    assert hass.states.get("select.home_roof_charge_mode").state == "off"
    assert hass.states.get("switch.home_roof_solargrid_low_tariff_only").state == "on"
    assert hass.states.get("switch.home_roof_battery_discharge_hold").state == "off"


async def test_old_version_refused(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock, health={**HEALTH, "version": "1.1.0 (abc)"})
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_not_polled_yet_retries(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/health", json=HEALTH)
    aioclient_mock.get(f"{BASE}/status", status=503, json={"detail": "No poll yet"})
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_unavailable_on_503_and_connection_loss(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    entity = "sensor.home_roof_solar_power"
    assert hass.states.get(entity).state == "3200.0"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/status", status=503, json={"detail": "No poll yet"})
    await _poll(hass, freezer)
    assert hass.states.get(entity).state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    mock_api(aioclient_mock)
    await _poll(hass, freezer)
    assert hass.states.get(entity).state == "3200.0"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/status", exc=aiohttp.ClientConnectionError())
    await _poll(hass, freezer)
    assert hass.states.get(entity).state == STATE_UNAVAILABLE


async def test_401_at_runtime_starts_reauth(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/status", status=401)
    await _poll(hass, freezer)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_unload(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED


async def test_plan_figures_only_while_their_mode_drives(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """/status carries the day plan in every mode; the sensors show it only in Forecasted."""
    plan = {"reason": "No chargeable window today", "evBudgetWh": 4200.0}
    coordinator = loaded_entry.runtime_data.status
    coordinator.async_set_updated_data({**STATUS, "mode": "off", "dayPlan": plan})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.home_roof_plan_state").state == "unknown"
    assert hass.states.get("sensor.home_roof_ev_energy_budget").state == "unknown"

    coordinator.async_set_updated_data({**STATUS, "mode": "forecasted", "dayPlan": plan})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.home_roof_plan_state").state == "No chargeable window today"
    assert hass.states.get("sensor.home_roof_ev_energy_budget").state == "4.2"

    fast = {"deliveredEnergyWh": 1500.0, "requiredEnergyWh": 20000.0}
    coordinator.async_set_updated_data({**STATUS, "mode": "solar", "fastCharge": fast})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.home_roof_fast_delivered").state == "unknown"
