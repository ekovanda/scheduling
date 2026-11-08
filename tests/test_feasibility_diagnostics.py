"""Unit and integration tests for Pre-Flight Consistency and Infeasibility Diagnostics."""

from datetime import date

from starlette.testclient import TestClient

from app.persistence.models import InfeasibilityCategory
from app.scheduler.feasibility import validate_pre_assigned_consistency
from app.scheduler.models import (
    Beruf,
    PreAssignedShift,
    ShiftType,
    Staff,
    Vacation,
)


def _make_tfa(
    name: str = "TFA Test",
    ident: str = "TFA1",
    nd_max_consecutive: int | None = 2,
    nd_exceptions: list[int] | None = None,
    nd_alone: bool = True,
) -> Staff:
    return Staff(
        name=name,
        identifier=ident,
        adult=True,
        hours=40,
        reception=False,
        nd_possible=True,
        nd_alone=nd_alone,
        nd_min_consecutive=2,
        nd_max_consecutive=nd_max_consecutive,
        nd_exceptions=nd_exceptions or [],
        beruf=Beruf.TFA,
    )


def _make_azubi(
    name: str = "Azubi Test",
    ident: str = "AZU1",
    adult: bool = True,
    nd_max_consecutive: int | None = 2,
    nd_exceptions: list[int] | None = None,
) -> Staff:
    return Staff(
        name=name,
        identifier=ident,
        adult=adult,
        hours=40,
        reception=False,
        nd_possible=True,
        nd_alone=False,
        nd_min_consecutive=2,
        nd_max_consecutive=nd_max_consecutive,
        nd_exceptions=nd_exceptions or [],
        beruf=Beruf.AZUBI,
    )


def test_preassigned_same_day_overlap() -> None:
    """Detect same-day double booking on a single staff member."""
    tfa = _make_tfa()
    pa1 = PreAssignedShift(
        shift_date=date(2027, 3, 26),
        shift_type=ShiftType.NIGHT_FRI_SAT,
        staff_identifier="TFA1",
    )
    pa2 = PreAssignedShift(
        shift_date=date(2027, 3, 26),
        shift_type=ShiftType.SUNDAY_10_22,
        staff_identifier="TFA1",
    )
    diags = validate_pre_assigned_consistency(
        pre_assigned=[pa1, pa2],
        staff_list=[tfa],
        vacations=[],
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
    )
    same_day_errors = [d for d in diags if d.category == InfeasibilityCategory.PREASSIGNED_SAME_DAY]
    assert len(same_day_errors) == 1
    assert "Doppelbelegung" in same_day_errors[0].title
    assert "TFA1" in same_day_errors[0].affected_staff_ids


def test_preassigned_consecutive_cap_overrun() -> None:
    """Detect streak exceeding nd_max_consecutive."""
    tfa = _make_tfa(nd_max_consecutive=2)
    # 3 consecutive nights: Thu, Fri, Sat
    pa_list = [
        PreAssignedShift(shift_date=date(2027, 3, 25), shift_type=ShiftType.NIGHT_THU_FRI, staff_identifier="TFA1"),
        PreAssignedShift(shift_date=date(2027, 3, 26), shift_type=ShiftType.NIGHT_FRI_SAT, staff_identifier="TFA1"),
        PreAssignedShift(shift_date=date(2027, 3, 27), shift_type=ShiftType.NIGHT_SAT_SUN, staff_identifier="TFA1"),
    ]
    diags = validate_pre_assigned_consistency(
        pre_assigned=pa_list,
        staff_list=[tfa],
        vacations=[],
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
    )
    cap_errors = [d for d in diags if d.category == InfeasibilityCategory.PREASSIGNED_CONSECUTIVE_CAP]
    assert len(cap_errors) == 1
    assert "Höchstgrenze aufeinanderfolgender Nächte" in cap_errors[0].title
    assert len(cap_errors[0].affected_dates) == 3


def test_preassigned_blocked_weekday() -> None:
    """Detect shift on weekday blocked by nd_exceptions (e.g. Thursday = 4)."""
    tfa = _make_tfa(nd_exceptions=[1, 4])  # Monday and Thursday blocked
    pa = PreAssignedShift(
        shift_date=date(2027, 3, 25),  # 25.03.2027 is a Thursday
        shift_type=ShiftType.NIGHT_THU_FRI,
        staff_identifier="TFA1",
    )
    diags = validate_pre_assigned_consistency(
        pre_assigned=[pa],
        staff_list=[tfa],
        vacations=[],
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
    )
    weekday_errors = [d for d in diags if d.category == InfeasibilityCategory.PREASSIGNED_BLOCKED_WEEKDAY]
    assert len(weekday_errors) == 1
    assert "Donnerstag" in weekday_errors[0].message


def test_preassigned_absence_collision() -> None:
    """Detect pre-assigned shift on a day with approved vacation."""
    tfa = _make_tfa()
    vacation = Vacation(
        identifier="TFA1",
        start_date=date(2027, 3, 20),
        end_date=date(2027, 3, 27),
        description="Urlaub",
    )
    pa = PreAssignedShift(
        shift_date=date(2027, 3, 25),
        shift_type=ShiftType.NIGHT_THU_FRI,
        staff_identifier="TFA1",
    )
    diags = validate_pre_assigned_consistency(
        pre_assigned=[pa],
        staff_list=[tfa],
        vacations=[vacation],
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
    )
    absence_errors = [d for d in diags if d.category == InfeasibilityCategory.PREASSIGNED_ABSENCE_COLLISION]
    assert len(absence_errors) == 1
    assert "Urlaub" in absence_errors[0].message


def test_preassigned_solo_unqualified_night() -> None:
    """Detect closed night assigned alone to someone with nd_alone=False."""
    azubi = _make_azubi(ident="AZU1")  # nd_alone=False
    pa = PreAssignedShift(
        shift_date=date(2027, 3, 25),  # Thursday night (closed)
        shift_type=ShiftType.NIGHT_THU_FRI,
        staff_identifier="AZU1",
    )
    diags = validate_pre_assigned_consistency(
        pre_assigned=[pa],
        staff_list=[azubi],
        vacations=[],
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
    )
    solo_errors = [d for d in diags if d.category == InfeasibilityCategory.PREASSIGNED_SOLO_UNQUALIFIED]
    assert len(solo_errors) == 1
    assert "Alleindienst" in solo_errors[0].title


def test_preassigned_open_night_missing_tfa() -> None:
    """Detect open night with two Azubis and no qualified TFA."""
    azu1 = _make_azubi(name="Azubi 1", ident="AZU1")
    azu2 = _make_azubi(name="Azubi 2", ident="AZU2")
    pa1 = PreAssignedShift(shift_date=date(2027, 3, 26), shift_type=ShiftType.NIGHT_FRI_SAT, staff_identifier="AZU1")
    pa2 = PreAssignedShift(shift_date=date(2027, 3, 26), shift_type=ShiftType.NIGHT_FRI_SAT, staff_identifier="AZU2")
    diags = validate_pre_assigned_consistency(
        pre_assigned=[pa1, pa2],
        staff_list=[azu1, azu2],
        vacations=[],
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
    )
    pairing_errors = [d for d in diags if d.category == InfeasibilityCategory.PREASSIGNED_PAIRING_UNQUALIFIED]
    assert len(pairing_errors) >= 1
    assert any("TFA" in e.message or "Azubi-Doppel" in e.title for e in pairing_errors)


def test_validate_feasibility_api_endpoint(client: TestClient) -> None:
    """Test POST /api/v1/quarters/{key}/validate-feasibility endpoint."""
    # 1. Onboard TFA
    client.post(
        "/api/v1/staff",
        json={
            "id": "TFA_KS",
            "identifier": "KS",
            "name": "Kaitlyn S.",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
            "nd_alone": True,
            "nd_max_consecutive": 2,
            "nd_exceptions": [4],  # Thursday blocked
        },
    )

    # 2. Add conflicting pre-assigned shift on Thursday
    client.post(
        "/api/v1/preassigned",
        json={
            "id": "PA_01",
            "staff_id": "TFA_KS",
            "staff_identifier": "KS",
            "shift_date": "2027-03-25",  # Thursday
            "shift_type": "N_Do-Fr",
        },
    )

    # 3. Call validate-feasibility
    resp = client.post("/api/v1/quarters/2027-Q1/validate-feasibility")
    assert resp.status_code == 200
    report = resp.json()
    assert report["is_feasible"] is False
    assert report["blocking_error_count"] >= 1
    assert any("Donnerstag" in d["message"] for d in report["diagnostics"])


def test_generate_fails_fast_on_infeasible_preassignments(client: TestClient) -> None:
    """Verify generate rejects immediately when hard pre-assignment conflicts exist."""
    # 1. Onboard staff with max 2 consecutive nights
    client.post(
        "/api/v1/staff",
        json={
            "id": "TFA_KS",
            "identifier": "KS",
            "name": "Kaitlyn S.",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
            "nd_alone": True,
            "nd_max_consecutive": 2,
        },
    )

    # 2. Pre-assign 3 consecutive nights
    for day in [25, 26, 27]:
        client.post(
            "/api/v1/preassigned",
            json={
                "id": f"PA_{day}",
                "staff_id": "TFA_KS",
                "staff_identifier": "KS",
                "shift_date": f"2027-03-{day}",
                "shift_type": "N_Fr-Sa" if day == 26 else "N_Sa-So" if day == 27 else "N_Do-Fr",
            },
        )

    # 3. Trigger generate -> returns FAILED SolverJobRecord with diagnostics immediately
    resp = client.post("/api/v1/quarters/2027-Q1/generate")
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "FAILED"
    assert "Vorprüfung fehlgeschlagen" in job["error"]
    assert len(job["diagnostics"]) >= 1
    assert any(d["category"] == "PREASSIGNED_CONSECUTIVE_CAP" for d in job["diagnostics"])


def test_accept_feasibility_violation_lifecycle(client: TestClient) -> None:
    """Verify accepting and revoking violations changes feasibility status."""
    # 1. Onboard staff with weekday restriction
    client.post(
        "/api/v1/staff",
        json={
            "id": "TFA_KS2",
            "identifier": "KS2",
            "name": "Kaitlyn S. Two",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
            "nd_alone": True,
            "nd_max_consecutive": 2,
            "nd_exceptions": [4],
        },
    )

    # 2. Pre-assign conflicting shift
    client.post(
        "/api/v1/preassigned",
        json={
            "id": "PA_KS2_01",
            "staff_id": "TFA_KS2",
            "staff_identifier": "KS2",
            "shift_date": "2027-03-25",
            "shift_type": "N_Do-Fr",
        },
    )

    # 3. Validate -> must be infeasible with can_be_accepted=True
    resp = client.post("/api/v1/quarters/2027-Q1/validate-feasibility")
    assert resp.status_code == 200
    report = resp.json()
    assert report["is_feasible"] is False
    target = next(d for d in report["diagnostics"] if "KS2" in d["affected_staff_ids"])
    assert target["can_be_accepted"] is True
    assert target["is_accepted"] is False
    assert target["id"] != ""
    assert "PA_KS2_01" in target["pre_assigned_ids"]

    # 4. Accept violation
    v_id = target["id"]
    accept_resp = client.post(
        "/api/v1/quarters/2027-Q1/accept-feasibility-violation",
        json={"violation_id": v_id, "accepted": True},
    )
    assert accept_resp.status_code == 200
    acc_report = accept_resp.json()
    acc_target = next(d for d in acc_report["diagnostics"] if d["id"] == v_id)
    assert acc_target["is_accepted"] is True

    # 5. Revoke violation
    revoke_resp = client.post(
        "/api/v1/quarters/2027-Q1/accept-feasibility-violation",
        json={"violation_id": v_id, "accepted": False},
    )
    assert revoke_resp.status_code == 200
    rev_report = revoke_resp.json()
    rev_target = next(d for d in rev_report["diagnostics"] if d["id"] == v_id)
    assert rev_target["is_accepted"] is False
