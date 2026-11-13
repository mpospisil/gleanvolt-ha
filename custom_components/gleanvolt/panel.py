"""The Gleanvolt panel and card, shipped with the integration so nobody pastes YAML.

``frontend/gleanvolt.js`` is served from the integration's own folder and loaded on every page, which
puts a Gleanvolt card in the card picker. A sidebar panel shows it for every installation; it is
registered with the first loaded config entry and removed with the last.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

URL_BASE = f"/{DOMAIN}_static"
FILE = "gleanvolt.js"
PANEL_URL_PATH = DOMAIN
PANEL_ELEMENT = "gleanvolt-panel"
_REGISTERED = f"{DOMAIN}_frontend"
_PANEL = f"{DOMAIN}_panel"
_FOLDER = Path(__file__).parent / "frontend"


def _fingerprint() -> str:
    """Busts the browser's cache whenever the file changes, release or not."""
    return hashlib.sha256((_FOLDER / FILE).read_bytes()).hexdigest()[:12]


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the module, load it on every page, and show the sidebar panel. Idempotent."""
    # Without the frontend (as in the test harness) there is nothing to show it in.
    if hass.http is None or "frontend" not in hass.config.components:
        return

    from homeassistant.components import frontend, panel_custom
    from homeassistant.components.http import StaticPathConfig

    if _REGISTERED not in hass.data:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(_FOLDER), cache_headers=False)]
        )
        url = f"{URL_BASE}/{FILE}?v={await hass.async_add_executor_job(_fingerprint)}"
        frontend.add_extra_js_url(hass, url)
        hass.data[_REGISTERED] = url

    if not hass.data.get(_PANEL):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title="Gleanvolt",
            sidebar_icon="mdi:ev-station",
            module_url=hass.data[_REGISTERED],
            require_admin=False,
        )
        hass.data[_PANEL] = True


def async_remove_panel(hass: HomeAssistant) -> None:
    """With the last installation gone, the sidebar entry goes too. The module stays loaded."""
    if not hass.data.pop(_PANEL, False):
        return
    from homeassistant.components import frontend

    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
