"""Numbers: amounts held for the next fast or targeted start, restored across a restart."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HeldNumberDescription(NumberEntityDescription):
    draft: str


def _kwh(key: str, draft: str) -> HeldNumberDescription:
    return HeldNumberDescription(
        key=key,
        draft=draft,
        device_class=NumberDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        native_min_value=0.5,
        native_max_value=200,
        native_step=0.5,
        mode=NumberMode.BOX,
    )


def _soc(key: str, draft: str) -> HeldNumberDescription:
    return HeldNumberDescription(
        key=key,
        draft=draft,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    )


NUMBERS: tuple[HeldNumberDescription, ...] = (
    _kwh("fast_energy", "fast_energy_kwh"),
    _soc("fast_target_soc", "fast_target_soc"),
    _kwh("target_energy", "target_energy_kwh"),
    _soc("target_soc", "target_soc"),
    _soc("target_rest_soc", "rest_soc"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(HeldNumber(runtime, description) for description in NUMBERS)


class HeldNumber(GleanvoltEntity, RestoreNumber):
    entity_description: HeldNumberDescription

    def __init__(self, runtime: GleanvoltRuntime, description: HeldNumberDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            setattr(self.runtime.drafts, self.entity_description.draft, last.native_value)

    @property
    def native_value(self) -> float | None:
        return getattr(self.runtime.drafts, self.entity_description.draft)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.runtime.drafts, self.entity_description.draft, value)
        self.async_write_ha_state()
