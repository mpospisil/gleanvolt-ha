"""What the select and the services send."""

from __future__ import annotations

from datetime import datetime

from custom_components.gleanvolt.payload import Drafts, start_from_drafts, target_body

NOW = datetime.fromisoformat("2026-11-13T10:00:00+01:00")
DEPART = datetime.fromisoformat("2026-11-14T07:00:00+01:00")


def test_plain_modes_send_only_the_mode() -> None:
    assert start_from_drafts("solar", Drafts(), NOW) == {"mode": "solar"}
    assert start_from_drafts("solar_grid", Drafts(), NOW) == {"mode": "solarGrid"}
    assert start_from_drafts("forecasted", Drafts(), NOW) == {"mode": "forecasted"}


def test_fast_full_sends_no_limit() -> None:
    assert start_from_drafts("fast_no_battery", Drafts(), NOW) == {"mode": "fastNoBattery"}


def test_fast_energy_in_wh_with_departure() -> None:
    drafts = Drafts(fast_basis="energy", fast_energy_kwh=20.5, fast_depart_by=DEPART)
    assert start_from_drafts("fast_no_battery", drafts, NOW) == {
        "mode": "fastNoBattery",
        "fast": {"basis": "energy", "energyWh": 20500, "departBy": "2026-11-14T07:00:00+01:00"},
    }


def test_fast_departure_in_the_past_means_now() -> None:
    past = datetime.fromisoformat("2026-11-13T07:00:00+01:00")
    drafts = Drafts(fast_basis="soc", fast_target_soc=80, fast_depart_by=past)
    assert start_from_drafts("fast_no_battery", drafts, NOW)["fast"] == {
        "basis": "soc",
        "targetSocPercent": 80,
    }


def test_targeted_from_drafts() -> None:
    drafts = Drafts(target_energy_kwh=22, depart_by=DEPART)
    assert start_from_drafts("targeted", drafts, NOW) == {
        "mode": "targeted",
        "target": {
            "energyWh": 22000,
            "departBy": "2026-11-14T07:00:00+01:00",
            "priority": "cheapest",
        },
    }


def test_targeted_with_nothing_held_leaves_the_reason_to_the_controller() -> None:
    assert start_from_drafts("targeted", Drafts(), NOW) == {
        "mode": "targeted",
        "target": {"priority": "cheapest"},
    }


def test_targeted_options() -> None:
    body = target_body("soc", 10, 80, DEPART, "just_in_time", 50, True, True)
    assert body == {
        "targetSocPercent": 80,
        "departBy": "2026-11-14T07:00:00+01:00",
        "priority": "justInTime",
        "restSocPercent": 50,
        "editable": {"maxGridEnergyWh": 0, "lowTariffOnly": True},
    }


def test_rest_soc_only_with_just_in_time() -> None:
    assert "restSocPercent" not in target_body(
        "energy", 10, None, DEPART, "cheapest", 50, False, False
    )


def test_service_picks_whichever_amount_is_given() -> None:
    assert target_body(None, None, 70, DEPART, None, None, False, False)["targetSocPercent"] == 70
    assert target_body(None, 12, None, DEPART, None, None, False, False)["energyWh"] == 12000
