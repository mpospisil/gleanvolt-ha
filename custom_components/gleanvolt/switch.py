"""Switches: four that act on the controller now, two held for the next targeted start."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltCoordinatorEntity, GleanvoltEntity, raise_for_controller, resolve

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            BatteryHoldSwitch(runtime),
            LowTariffOnlySwitch(runtime, "fast_low_tariff_only", "fastNoBattery"),
            LowTariffOnlySwitch(runtime, "solar_grid_low_tariff_only", "solarGrid"),
            UntilFullSwitch(runtime),
            HeldSwitch(runtime, "target_sun_only", "sun_only"),
            HeldSwitch(runtime, "target_low_tariff_only", "low_tariff_only"),
        ]
    )


class BatteryHoldSwitch(GleanvoltCoordinatorEntity, SwitchEntity):
    """``PUT /battery-hold``. Unavailable while the hold is disabled in configuration (409)."""

    def __init__(self, runtime: GleanvoltRuntime) -> None:
        super().__init__(runtime, "battery_discharge_hold", runtime.status)

    @property
    def available(self) -> bool:
        return super().available and resolve(self.coordinator.data, "batteryHold.enabled") is True

    @property
    def is_on(self) -> bool | None:
        return resolve(self.coordinator.data, "batteryHold.requested")

    @raise_for_controller
    async def async_turn_on(self, **kwargs: Any) -> None:
        self.runtime.apply_action(await self.runtime.client.set_battery_hold(True))

    @raise_for_controller
    async def async_turn_off(self, **kwargs: Any) -> None:
        self.runtime.apply_action(await self.runtime.client.set_battery_hold(False))


class LowTariffOnlySwitch(GleanvoltCoordinatorEntity, SwitchEntity):
    """``PUT /charging/low-tariff-only``, one field of it; the other is left as it is."""

    def __init__(self, runtime: GleanvoltRuntime, key: str, field: str) -> None:
        super().__init__(runtime, key, runtime.slow)
        self._field = field

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return resolve(data.low_tariff_only, self._field) if data else None

    async def _set(self, value: bool) -> None:
        if self._field == "fastNoBattery":
            result = await self.runtime.client.set_low_tariff_only(fast_no_battery=value)
        else:
            result = await self.runtime.client.set_low_tariff_only(solar_grid=value)
        self.runtime.slow.replace(low_tariff_only=result)

    @raise_for_controller
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    @raise_for_controller
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class UntilFullSwitch(GleanvoltCoordinatorEntity, SwitchEntity):
    """``PUT /charging/until-full``. Starts nothing on its own."""

    def __init__(self, runtime: GleanvoltRuntime) -> None:
        super().__init__(runtime, "forecasted_until_full", runtime.slow)

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return resolve(data.until_full, "untilFull") if data else None

    @raise_for_controller
    async def async_turn_on(self, **kwargs: Any) -> None:
        self.runtime.slow.replace(until_full=await self.runtime.client.set_until_full(True))

    @raise_for_controller
    async def async_turn_off(self, **kwargs: Any) -> None:
        self.runtime.slow.replace(until_full=await self.runtime.client.set_until_full(False))


class HeldSwitch(GleanvoltEntity, SwitchEntity, RestoreEntity):
    """A targeted option held for the next start, restored across a restart."""

    def __init__(self, runtime: GleanvoltRuntime, key: str, draft: str) -> None:
        super().__init__(runtime, key)
        self._draft = draft

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            setattr(self.runtime.drafts, self._draft, last.state == "on")

    @property
    def is_on(self) -> bool:
        return getattr(self.runtime.drafts, self._draft)

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.runtime.drafts, self._draft, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.runtime.drafts, self._draft, False)
        self.async_write_ha_state()
