"""Stop charging."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltCoordinatorEntity, raise_for_controller

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([StopChargingButton(entry.runtime_data)])


class StopChargingButton(GleanvoltCoordinatorEntity, ButtonEntity):
    """``POST /charging/stop``: writes Stop to the charger and returns the mode to Off."""

    def __init__(self, runtime: GleanvoltRuntime) -> None:
        super().__init__(runtime, "stop_charging", runtime.status)

    @raise_for_controller
    async def async_press(self) -> None:
        self.runtime.apply_action(await self.runtime.client.stop())
