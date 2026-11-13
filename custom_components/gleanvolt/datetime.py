"""Departures held for the next fast or targeted start, restored across a restart."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .data import GleanvoltConfigEntry, GleanvoltRuntime
from .entity import GleanvoltEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GleanvoltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            HeldDateTime(runtime, "fast_departure", "fast_depart_by"),
            HeldDateTime(runtime, "departure", "depart_by"),
        ]
    )


class HeldDateTime(GleanvoltEntity, DateTimeEntity, RestoreEntity):
    def __init__(self, runtime: GleanvoltRuntime, key: str, draft: str) -> None:
        super().__init__(runtime, key)
        self._draft = draft

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and (restored := dt_util.parse_datetime(last.state)) is not None:
            setattr(self.runtime.drafts, self._draft, restored)

    @property
    def native_value(self) -> datetime | None:
        return getattr(self.runtime.drafts, self._draft)

    async def async_set_value(self, value: datetime) -> None:
        setattr(self.runtime.drafts, self._draft, value)
        self.async_write_ha_state()
