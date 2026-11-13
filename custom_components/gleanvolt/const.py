"""Constants for the Gleanvolt integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "gleanvolt"

DEFAULT_PORT: Final = 8090
CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 10
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 60

SLOW_INTERVAL: Final = timedelta(seconds=60)
HEALTH_INTERVAL: Final = timedelta(minutes=5)

# The oldest Gleanvolt whose API has everything this release uses.
MIN_VERSION: Final = (1, 2, 0)
MIN_VERSION_TEXT: Final = "1.2.0"

# The API's camel-cased enum values <-> Home Assistant's snake-cased state values.
MODES: Final = {
    "off": "off",
    "solar": "solar",
    "forecasted": "forecasted",
    "solarGrid": "solar_grid",
    "fastNoBattery": "fast_no_battery",
    "targeted": "targeted",
}
MODES_REVERSED: Final = {value: key for key, value in MODES.items()}

FAST_BASES: Final = ("full", "energy", "soc")
TARGET_BASES: Final = ("energy", "soc")
PRIORITIES: Final = {"cheapest": "cheapest", "justInTime": "just_in_time"}
PRIORITIES_REVERSED: Final = {value: key for key, value in PRIORITIES.items()}


def snake(value: str | None) -> str | None:
    """``suspendedEvse`` -> ``suspended_evse``."""
    if value is None:
        return None
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in value)
