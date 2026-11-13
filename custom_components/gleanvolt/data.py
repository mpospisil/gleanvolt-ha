"""What a loaded config entry carries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

from .payload import Drafts

if TYPE_CHECKING:
    from .api import GleanvoltClient
    from .coordinator import GleanvoltSlowCoordinator, GleanvoltStatusCoordinator


@dataclass
class GleanvoltRuntime:
    client: GleanvoltClient
    status: GleanvoltStatusCoordinator
    slow: GleanvoltSlowCoordinator
    system_id: str
    system_name: str
    version: str
    drafts: Drafts = field(default_factory=Drafts)

    def apply_action(self, result: dict[str, Any]) -> None:
        """Every action answers with the controller's state afterwards: show it now."""
        if isinstance(result.get("status"), dict):
            self.status.async_set_updated_data(result["status"])


type GleanvoltConfigEntry = ConfigEntry[GleanvoltRuntime]
