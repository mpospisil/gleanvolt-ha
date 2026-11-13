"""Selects: the charge mode, which acts now, and three parameters held for the next start."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import FAST_BASES, MODES, PRIORITIES, TARGET_BASES
from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltCoordinatorEntity, GleanvoltEntity, raise_for_controller
from .payload import start_from_drafts

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            ChargeModeSelect(runtime),
            HeldSelect(runtime, "fast_basis", "fast_basis", list(FAST_BASES)),
            HeldSelect(runtime, "target_basis", "target_basis", list(TARGET_BASES)),
            HeldSelect(runtime, "charge_priority", "priority", list(PRIORITIES.values())),
        ]
    )


class ChargeModeSelect(GleanvoltCoordinatorEntity, SelectEntity):
    """Shows the mode from ``/status``. Picking one starts it with the held parameters; Off stops.

    A refusal is raised to the person who picked it, and the select shows the real mode again on the
    next refresh.
    """

    def __init__(self, runtime: GleanvoltRuntime) -> None:
        super().__init__(runtime, "charge_mode", runtime.status)
        self._attr_options = list(MODES.values())

    @property
    def current_option(self) -> str | None:
        return MODES.get(self.coordinator.data.get("mode")) if self.coordinator.data else None

    @raise_for_controller
    async def async_select_option(self, option: str) -> None:
        try:
            if option == "off":
                result = await self.runtime.client.stop()
            else:
                result = await self.runtime.client.start(
                    start_from_drafts(option, self.runtime.drafts, dt_util.now())
                )
        except Exception:
            # Snap back to what the controller is doing, not what was asked for.
            self.async_write_ha_state()
            raise
        self.runtime.apply_action(result)


class HeldSelect(GleanvoltEntity, SelectEntity, RestoreEntity):
    """A parameter for the next start, kept in Home Assistant and restored across a restart."""

    def __init__(self, runtime: GleanvoltRuntime, key: str, draft: str, options: list[str]) -> None:
        super().__init__(runtime, key)
        self._draft = draft
        self._attr_options = options

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self.options:
            setattr(self.runtime.drafts, self._draft, last.state)

    @property
    def current_option(self) -> str | None:
        return getattr(self.runtime.drafts, self._draft)

    async def async_select_option(self, option: str) -> None:
        setattr(self.runtime.drafts, self._draft, option)
        self.async_write_ha_state()
