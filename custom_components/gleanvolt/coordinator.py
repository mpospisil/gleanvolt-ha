"""The two polls: the live status, and the slower rest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    GleanvoltApiDisabledError,
    GleanvoltAuthError,
    GleanvoltClient,
    GleanvoltError,
    GleanvoltNotReadyError,
)
from .const import DOMAIN, HEALTH_INTERVAL, SLOW_INTERVAL

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


def _failed(err: GleanvoltError) -> Exception:
    """What a failed poll becomes: a reauth on 401, otherwise unavailable until the next one."""
    if isinstance(err, GleanvoltAuthError):
        return ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth")
    if isinstance(err, GleanvoltApiDisabledError):
        return UpdateFailed(translation_domain=DOMAIN, translation_key="api_disabled")
    if isinstance(err, GleanvoltNotReadyError):
        return UpdateFailed(translation_domain=DOMAIN, translation_key="not_ready")
    return UpdateFailed(
        translation_domain=DOMAIN,
        translation_key="cannot_connect",
        translation_placeholders={"error": str(err)},
    )


class GleanvoltStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """``GET /status`` every few seconds. 503 (no poll yet) and no answer both mean unavailable."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GleanvoltClient,
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} status",
            update_interval=interval,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.status()
        except GleanvoltError as err:
            raise _failed(err) from err


@dataclass
class SlowData:
    """What changes slowly: the car's reading, the tariff, the two option flags and health."""

    vehicle: dict[str, Any] = field(default_factory=dict)
    tariff: dict[str, Any] = field(default_factory=dict)
    low_tariff_only: dict[str, Any] = field(default_factory=dict)
    until_full: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)

    def source(self, name: str) -> dict[str, Any]:
        return getattr(self, name)


class GleanvoltSlowCoordinator(DataUpdateCoordinator[SlowData]):
    """Every minute: vehicle, tariff and the two options; ``/health`` every five.

    Never ``/forecast?weather=true``: that fetches weather on every call.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GleanvoltClient,
        health: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} slow",
            update_interval=SLOW_INTERVAL,
        )
        self.client = client
        self._health = health
        self._health_at: datetime = dt_util.utcnow()

    async def _async_update_data(self) -> SlowData:
        try:
            if dt_util.utcnow() - self._health_at >= HEALTH_INTERVAL:
                self._health = await self.client.health()
                self._health_at = dt_util.utcnow()
            return SlowData(
                vehicle=await self.client.vehicle(),
                tariff=await self.client.tariff(),
                low_tariff_only=await self.client.low_tariff_only(),
                until_full=await self.client.until_full(),
                health=self._health,
            )
        except GleanvoltError as err:
            raise _failed(err) from err

    def replace(self, **changes: dict[str, Any]) -> None:
        """Push what an action answered with, rather than waiting a minute to show it."""
        current = self.data or SlowData(health=self._health)
        self.async_set_updated_data(SlowData(**{**current.__dict__, **changes}))
