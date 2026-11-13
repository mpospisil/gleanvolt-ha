"""The diagnostics download never carries the key."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gleanvolt.diagnostics import async_get_config_entry_diagnostics

from .conftest import KEY


async def test_key_redacted(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    result = await async_get_config_entry_diagnostics(hass, loaded_entry)
    assert result["entry"]["data"]["api_key"] == "**REDACTED**"
    assert KEY not in str(result)
    assert result["status"]["mode"] == "off"
    assert result["health"]["systemId"] == "home-roof"
