"""The drift guard: every route, field read and field sent exists in contract/openapi.json (v1.2.0)."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.gleanvolt.api import API_PREFIX, REQUEST_SCHEMAS, ROUTES
from custom_components.gleanvolt.binary_sensor import BINARY_SENSORS
from custom_components.gleanvolt.payload import Drafts, fast_body, start_from_drafts, target_body
from custom_components.gleanvolt.sensor import GRID_PRICE, SENSORS

CONTRACT = json.loads((Path(__file__).parent.parent / "contract" / "openapi.json").read_text())
SCHEMAS = CONTRACT["components"]["schemas"]

SOURCE_SCHEMAS = {
    "status": "StatusResponse",
    "health": "HealthResponse",
    "vehicle": "VehicleResponse",
    "tariff": "TariffResponse",
    "low_tariff_only": "LowTariffOnlyResponse",
    "until_full": "UntilFullResponse",
}

# Read by entities that are not descriptions.
EXTRA_READS = [
    ("status", "mode"),
    ("status", "batteryHold.enabled"),
    ("status", "batteryHold.requested"),
    ("low_tariff_only", "fastNoBattery"),
    ("low_tariff_only", "solarGrid"),
    ("until_full", "untilFull"),
    ("tariff", "currency"),
    ("health", "systemId"),
    ("health", "systemName"),
    ("health", "version"),
]


def _ref(schema: dict[str, Any]) -> str | None:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    for option in schema.get("oneOf", []) + schema.get("anyOf", []):
        if (ref := _ref(option)) is not None:
            return ref
    return None


def _walk(schema_name: str, path: str) -> dict[str, Any]:
    """The property schema at ``path``, or a failed assertion naming where it broke."""
    schema = SCHEMAS[schema_name]
    for part in path.split("."):
        properties = schema.get("properties", {})
        assert part in properties, f"{schema_name} has no '{part}' (in '{path}')"
        prop = properties[part]
        ref = _ref(prop)
        schema = SCHEMAS[ref] if ref else prop
        schema_name = ref or schema_name
    return schema


def test_contract_is_v1() -> None:
    assert CONTRACT["info"]["version"] == "v1"


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_route_exists(route: str) -> None:
    method, path, response = ROUTES[route]
    operation = CONTRACT["paths"].get(f"{API_PREFIX}{path}", {}).get(method.lower())
    assert operation is not None, f"{method} {path} is not in the contract"
    content = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert _ref(content) == response
    if route in REQUEST_SCHEMAS:
        body = operation["requestBody"]["content"]["application/json"]["schema"]
        assert _ref(body) == REQUEST_SCHEMAS[route]


@pytest.mark.parametrize(
    ("source", "path"),
    [(d.source, d.path) for d in (*SENSORS, GRID_PRICE, *BINARY_SENSORS)] + EXTRA_READS,
)
def test_field_read_exists(source: str, path: str) -> None:
    _walk(SOURCE_SCHEMAS[source], path)


def _assert_body(schema_name: str, body: dict[str, Any]) -> None:
    for key, value in body.items():
        prop = _walk(schema_name, key)
        if isinstance(value, dict):
            ref = _ref(SCHEMAS[schema_name]["properties"][key])
            assert ref is not None
            _assert_body(ref, value)
        if "enum" in prop:
            assert value in prop["enum"], f"{schema_name}.{key}={value!r}"


NOW = datetime.fromisoformat("2026-11-13T10:00:00+01:00")
DEPART = datetime.fromisoformat("2026-11-14T07:00:00+01:00")


@pytest.mark.parametrize(
    "body",
    [
        start_from_drafts("solar", Drafts(), NOW),
        start_from_drafts(
            "fast_no_battery",
            Drafts(fast_basis="energy", fast_energy_kwh=20, fast_depart_by=DEPART),
            NOW,
        ),
        start_from_drafts("fast_no_battery", Drafts(fast_basis="soc", fast_target_soc=60), NOW),
        start_from_drafts(
            "targeted",
            Drafts(
                target_basis="soc",
                target_soc=80,
                depart_by=DEPART,
                priority="just_in_time",
                rest_soc=50,
                sun_only=True,
                low_tariff_only=True,
            ),
            NOW,
        ),
    ],
)
def test_start_body_matches(body: dict[str, Any]) -> None:
    _assert_body("StartChargingRequest", body)
    for nested, schema in (
        ("fast", "FastChargeLimitBody"),
        ("target", "TargetedChargeRequestBody"),
    ):
        if nested in body:
            _assert_body(schema, body[nested])
            if "editable" in body[nested]:
                _assert_body("EditablePlanBody", body[nested]["editable"])
    if "fast" in body:
        assert body["fast"]["basis"] in SCHEMAS["FastChargeBasis"]["enum"]
    if "target" in body:
        assert body["target"]["priority"] in SCHEMAS["TargetedChargePriority"]["enum"]
    assert body["mode"] in SCHEMAS["ChargeControlMode"]["enum"]


def test_preview_body_matches() -> None:
    body = target_body(None, 22, None, DEPART, "cheapest", None, False, True)
    _assert_body("TargetedChargeRequestBody", body)
    _assert_body("EditablePlanBody", body["editable"])
    assert fast_body("full", None, None, None) is None
