"""Sensors: the live status, the car, the tariff, the running plans and health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import number
from .const import MODES, snake
from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltCoordinatorEntity, resolve

PARALLEL_UPDATES = 0


def _kwh(value: Any) -> float | None:
    wh = number(value)
    return None if wh is None else round(wh / 1000, 3)


def _km(value: Any) -> float | None:
    metres = number(value)
    return None if metres is None else round(metres / 1000, 1)


def _timestamp(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _text(value: Any) -> str | None:
    return value[:255] if isinstance(value, str) else None


def _enum(value: Any) -> str | None:
    return snake(value) if isinstance(value, str) else None


def _percent_of_one(value: Any) -> float | None:
    factor = number(value)
    return None if factor is None else round(factor * 100, 1)


@dataclass(frozen=True, kw_only=True)
class GleanvoltSensorDescription(SensorEntityDescription):
    """``path`` is read from ``source``; the contract test checks it against the OpenAPI document."""

    source: str = "status"
    path: str
    convert: Callable[[Any], Any] = number


def _power(key: str, path: str, **kwargs: Any) -> GleanvoltSensorDescription:
    return GleanvoltSensorDescription(
        key=key,
        path=path,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        **kwargs,
    )


def _current(key: str, path: str) -> GleanvoltSensorDescription:
    return GleanvoltSensorDescription(
        key=key,
        path=path,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    )


def _energy(
    key: str, path: str, source: str = "status", **kwargs: Any
) -> GleanvoltSensorDescription:
    """A figure in kWh. Plan figures carry no state class: they are not a meter."""
    return GleanvoltSensorDescription(
        key=key,
        path=path,
        source=source,
        convert=_kwh,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        **kwargs,
    )


def _soc(key: str, path: str, source: str = "status", **kwargs: Any) -> GleanvoltSensorDescription:
    return GleanvoltSensorDescription(
        key=key,
        path=path,
        source=source,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        **kwargs,
    )


def _time(key: str, path: str, source: str = "status", **kwargs: Any) -> GleanvoltSensorDescription:
    return GleanvoltSensorDescription(
        key=key,
        path=path,
        source=source,
        convert=_timestamp,
        device_class=SensorDeviceClass.TIMESTAMP,
        **kwargs,
    )


def _reason(key: str, path: str) -> GleanvoltSensorDescription:
    return GleanvoltSensorDescription(key=key, path=path, convert=_text)


CHARGER_STATUSES = [
    "available",
    "preparing",
    "charging",
    "finishing",
    "faulted",
    "unavailable",
    "reserved",
    "suspended_ev",
    "suspended_evse",
    "update",
    "card_activation",
    "start_delay",
    "charge_paused",
    "stopping",
    "unknown",
]

SENSORS: tuple[GleanvoltSensorDescription, ...] = (
    # Live data, from /status.
    GleanvoltSensorDescription(
        key="charge_mode",
        path="mode",
        convert=lambda value: MODES.get(value),
        device_class=SensorDeviceClass.ENUM,
        options=list(MODES.values()),
    ),
    GleanvoltSensorDescription(
        key="control_state",
        path="state",
        convert=_enum,
        device_class=SensorDeviceClass.ENUM,
        options=["disabled", "idle", "charging", "paused"],
    ),
    GleanvoltSensorDescription(
        key="charger_status",
        path="chargerStatus",
        convert=_enum,
        device_class=SensorDeviceClass.ENUM,
        options=CHARGER_STATUSES,
    ),
    _power("solar_power", "solarPowerWatts"),
    _power("forecast_solar_power", "forecastSolarPowerWatts"),
    _power("solar_surplus", "surplusWatts"),
    _power("grid_power", "gridPowerWatts"),
    _power("battery_power", "batteryPowerWatts"),
    _soc(
        "battery_soc",
        "batterySocPercent",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _power("ev_charging_power", "evChargerPowerWatts"),
    _current("ev_charging_current", "evChargingCurrentAmps"),
    _current("target_charging_current", "targetCurrentAmps"),
    _current("active_charging_current", "activeCurrentAmps"),
    _energy(
        "session_energy",
        "sessionEnergyWh",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    _power("battery_loan_power", "loanPowerWatts"),
    _energy(
        "battery_loaned_today",
        "loanedTodayWh",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    _energy("tomorrow_forecast", "tomorrowForecastWh"),
    # Forecasted: the day plan, unknown in every other mode.
    _reason("plan_state", "dayPlan.reason"),
    _energy("ev_energy_budget", "dayPlan.evBudgetWh"),
    _energy("projected_shortfall", "dayPlan.shortfallWh"),
    _energy("surplus_spill", "dayPlan.spillWh"),
    _energy("loan_headroom", "dayPlan.loanHeadroomWh"),
    _soc("required_soc_floor", "dayPlan.requiredSocFloorPercent"),
    _soc("trajectory_soc_floor", "dayPlan.trajectorySocFloorPercent"),
    _energy("forecast_remaining_today", "dayPlan.remainingPvWh"),
    GleanvoltSensorDescription(
        key="forecast_accuracy",
        path="dayPlan.biasFactor",
        convert=_percent_of_one,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    # Targeted: the running plan, unknown in every other mode.
    _reason("target_plan_state", "targetedPlan.reason"),
    _energy("target_forecast_surplus", "targetedPlan.forecastSurplusWh"),
    _energy("target_solar_energy", "targetedPlan.solarEnergyWh"),
    _energy("target_grid_energy", "targetedPlan.gridEnergyWh"),
    _energy("target_expected", "targetedPlan.expectedEnergyWh"),
    _energy("target_shortfall", "targetedPlan.shortfallWh"),
    _power(
        "target_charge_pace",
        "targetedPlan.requiredPaceWatts",
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
    ),
    _time("charging_from", "targetedPlan.gridStart"),
    _time("target_hold_until", "targetedPlan.holdUntil"),
    # FastNoBattery with an amount: progress, unknown otherwise.
    _energy("fast_delivered", "fastCharge.deliveredEnergyWh"),
    _energy("fast_target", "fastCharge.requiredEnergyWh"),
    _time("fast_start", "fastCharge.schedule.startNoLaterThan"),
    # The car, from /vehicle.
    _soc(
        "car_soc",
        "socPercent",
        source="vehicle",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GleanvoltSensorDescription(
        key="car_range",
        source="vehicle",
        path="rangeMetres",
        convert=_km,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
    ),
    _time("car_reading_age", "capturedAt", source="vehicle"),
    # The tariff, from /tariff.
    _time("tariff_change", "now.until", source="tariff"),
    # Health, from /health.
    _time(
        "last_poll_age",
        "lastPollAt",
        source="health",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    GleanvoltSensorDescription(
        key="version",
        source="health",
        path="version",
        convert=_text,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

GRID_PRICE = GleanvoltSensorDescription(
    key="grid_price",
    source="tariff",
    path="now.pricePerKwh",
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=2,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [
        GleanvoltSensor(runtime, description) for description in SENSORS
    ]
    entities.append(GleanvoltGridPrice(runtime, GRID_PRICE))
    async_add_entities(entities)


class GleanvoltSensor(GleanvoltCoordinatorEntity, SensorEntity):
    entity_description: GleanvoltSensorDescription

    def __init__(self, runtime: GleanvoltRuntime, description: GleanvoltSensorDescription) -> None:
        coordinator = runtime.status if description.source == "status" else runtime.slow
        super().__init__(runtime, description.key, coordinator)
        self.entity_description = description

    def _source(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if self.entity_description.source == "status":
            return data
        return data.source(self.entity_description.source) if data is not None else None

    @property
    def native_value(self) -> Any:
        description = self.entity_description
        return description.convert(resolve(self._source(), description.path))


class GleanvoltGridPrice(GleanvoltSensor):
    """What a grid kWh costs now, in the tariff's currency: the energy dashboard's current price."""

    @property
    def native_unit_of_measurement(self) -> str | None:
        currency = resolve(self._source(), "currency")
        return f"{currency}/kWh" if currency else None
