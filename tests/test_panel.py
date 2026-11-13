"""The panel and card the integration ships: its layout, and how it is registered."""

from __future__ import annotations

import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gleanvolt import panel

SCRIPT = (
    Path(__file__).parent.parent / "custom_components" / "gleanvolt" / "frontend" / "gleanvolt.js"
).read_text()


def _layout() -> dict:
    block = SCRIPT.split("// LAYOUT-BEGIN", 1)[1].split("// LAYOUT-END", 1)[0]
    return json.loads(block[block.index("{") : block.rindex("}") + 1])


def _keys(layout: dict) -> set[str]:
    keys = {*layout["top"], layout["picker"], layout["start"]}
    for items in layout["modes"].values():
        for item in items:
            if isinstance(item, str):
                keys.add(item)
            elif "entity" in item:
                keys.update((item["entity"], item["when"][0]))
    return keys


async def test_layout_names_only_real_entities(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Every "domain.key" in the card is an entity this integration makes, found the card's way."""
    made = {
        f"{entry.domain}.{entry.translation_key}"
        for entry in er.async_entries_for_config_entry(er.async_get(hass), loaded_entry.entry_id)
    }
    layout = _layout()
    assert sorted(_keys(layout) - made) == []
    # A tab per mode Charge mode can start, and the picker offers exactly those.
    picker = hass.states.get("select.home_roof_mode_to_start")
    assert list(layout["modes"]) == picker.attributes["options"]


async def test_conditions_use_real_states(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """A row shown only for a basis or priority names a state that select can actually have."""
    ids = {
        f"{entry.domain}.{entry.translation_key}": entry.entity_id
        for entry in er.async_entries_for_config_entry(er.async_get(hass), loaded_entry.entry_id)
    }
    for items in _layout()["modes"].values():
        for item in items:
            if isinstance(item, dict) and "when" in item:
                key, state = item["when"]
                assert state in hass.states.get(ids[key]).attributes["options"]


def test_mode_names_cover_every_tab() -> None:
    names = re.search(r"const MODE_NAMES = \{(.*?)\};", SCRIPT, re.S)[1]
    assert set(re.findall(r"(\w+):", names)) == set(_layout()["modes"])


async def test_registered_once_and_removed_with_the_last_entry(hass: HomeAssistant) -> None:
    hass.config.components.add("frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with (
        patch("homeassistant.components.frontend.add_extra_js_url") as add_js,
        patch(
            "homeassistant.components.panel_custom.async_register_panel", new=AsyncMock()
        ) as register,
        patch("homeassistant.components.frontend.async_remove_panel") as remove,
    ):
        await panel.async_register_frontend(hass)
        await panel.async_register_frontend(hass)

        hass.http.async_register_static_paths.assert_awaited_once()
        [static] = hass.http.async_register_static_paths.await_args.args[0]
        assert static.url_path == "/gleanvolt_static"
        assert static.path == str(Path(panel.__file__).parent / "frontend")
        add_js.assert_called_once()
        url = add_js.call_args.args[1]
        assert re.fullmatch(r"/gleanvolt_static/gleanvolt\.js\?v=[0-9a-f]{12}", url)
        register.assert_awaited_once()
        assert register.await_args.kwargs["module_url"] == url
        assert register.await_args.kwargs["webcomponent_name"] == "gleanvolt-panel"

        panel.async_remove_panel(hass)
        panel.async_remove_panel(hass)
        remove.assert_called_once()


async def test_nothing_without_the_frontend(hass: HomeAssistant) -> None:
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    await panel.async_register_frontend(hass)
    hass.http.async_register_static_paths.assert_not_awaited()
