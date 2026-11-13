"""Binary sensors: plugged in, charging, the hold, the car's feed, the tariff and health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltCoordinatorEntity, resolve

PARALLEL_UPDATES = 0


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


@dataclass(frozen=True, kw_only=True)
class GleanvoltBinarySensorDescription(BinarySensorEntityDescription):
    source: str = "status"
    path: str
    convert: Callable[[Any], bool | None] = _flag


BINARY_SENSORS: tuple[GleanvoltBinarySensorDescription, ...] = (
    GleanvoltBinarySensorDescription(
        key="car_connected",
        path="carConnected",
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    GleanvoltBinarySensorDescription(
        key="charging_now",
        path="state",
        convert=lambda value: None if value is None else value == "charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    GleanvoltBinarySensorDescription(
        key="battery_hold_active",
        path="batteryHold.active",
    ),
    GleanvoltBinarySensorDescription(
        key="dry_run",
        path="dryRun",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    GleanvoltBinarySensorDescription(
        key="car_reading_stale",
        source="vehicle",
        path="stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    # Unknown with no tariff: no tariff is not the same as high tariff.
    GleanvoltBinarySensorDescription(
        key="low_tariff",
        source="tariff",
        path="now.rate",
        convert=lambda value: None if value is None else value == "low",
    ),
    GleanvoltBinarySensorDescription(
        key="forecast_available",
        source="health",
        path="forecastAvailable",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        GleanvoltBinarySensor(runtime, description) for description in BINARY_SENSORS
    )


class GleanvoltBinarySensor(GleanvoltCoordinatorEntity, BinarySensorEntity):
    entity_description: GleanvoltBinarySensorDescription

    def __init__(
        self, runtime: GleanvoltRuntime, description: GleanvoltBinarySensorDescription
    ) -> None:
        coordinator = runtime.status if description.source == "status" else runtime.slow
        super().__init__(runtime, description.key, coordinator)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        description = self.entity_description
        data = self.coordinator.data
        if description.source != "status":
            data = data.source(description.source) if data is not None else None
        return description.convert(resolve(data, description.path))
