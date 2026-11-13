"""Start the mode picked in Mode to start, and stop charging."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltCoordinatorEntity, raise_for_controller
from .payload import start_from_drafts

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities([StartModeButton(runtime), StopChargingButton(runtime)])


class StopChargingButton(GleanvoltCoordinatorEntity, ButtonEntity):
    """``POST /charging/stop``: writes Stop to the charger and returns the mode to Off."""

    def __init__(self, runtime: GleanvoltRuntime) -> None:
        super().__init__(runtime, "stop_charging", runtime.status)

    @raise_for_controller
    async def async_press(self) -> None:
        self.runtime.apply_action(await self.runtime.client.stop())


class StartModeButton(GleanvoltCoordinatorEntity, ButtonEntity):
    """The web UI's Start on a tab: the mode in Mode to start, with that mode's held parameters."""

    def __init__(self, runtime: GleanvoltRuntime) -> None:
        super().__init__(runtime, "start_mode", runtime.status)

    @raise_for_controller
    async def async_press(self) -> None:
        drafts = self.runtime.drafts
        self.runtime.apply_action(
            await self.runtime.client.start(
                start_from_drafts(drafts.next_mode, drafts, dt_util.now())
            )
        )
