"""Tests for Staff model validation and loader normalization (Findings B1 and D1)."""

from pathlib import Path
import pytest

from app.scheduler.exceptions import StaffValidationError
from app.scheduler.file_loader import load_staff_from_file
from app.scheduler.models import Beruf, Staff, load_staff_from_csv


def test_tfa_blank_hours_raises_validation_error() -> None:
    """TFA with blank hours string raises StaffValidationError (B1)."""
    with pytest.raises(StaffValidationError, match="Missing required field 'hours'"):
        Staff(
            name="Alice",
            identifier="A1",
            adult=True,
            hours="",  # type: ignore[arg-type]
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
        )


def test_tfa_zero_hours_raises_validation_error() -> None:
    """TFA with zero hours raises StaffValidationError (B1)."""
    with pytest.raises(StaffValidationError, match="must have contracted weekly hours > 0"):
        Staff(
            name="Bob",
            identifier="B1",
            adult=True,
            hours=0,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
        )


def test_tfa_missing_required_field_raises_validation_error() -> None:
    """Non-vet missing required fields (e.g. nd_alone) raises StaffValidationError (B1)."""
    with pytest.raises(StaffValidationError, match="Missing required field 'nd_alone'"):
        Staff(
            name="Charlie",
            identifier="C1",
            adult=True,
            hours=38,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=None,  # type: ignore[arg-type]
        )


def test_vet_lenient_defaults_accepted() -> None:
    """Vet rows legitimately omit hours/adult/reception and receive defaults."""
    v = Staff(name="Dr. Vet", identifier="V1", beruf=Beruf.VET)
    assert v.beruf == Beruf.VET
    assert v.hours == 0
    assert v.adult is True
    assert v.nd_alone is True
    assert v.reception is False
    assert v.nd_min_consecutive == 2
    assert v.nd_max_consecutive == 2


def test_ambiguous_role_shortcuts_rejected() -> None:
    """Deprecated ambiguous shortcuts ('TA', 'Tierarzt') raise StaffValidationError."""
    with pytest.raises(StaffValidationError, match="deprecated and ambiguous"):
        Staff(name="Old TA", identifier="O1", adult=True, hours=40, beruf="TA", reception=False, nd_possible=True, nd_alone=True)  # type: ignore[arg-type]

    with pytest.raises(StaffValidationError, match="deprecated and ambiguous"):
        Staff(name="Old TA", identifier="O2", adult=True, hours=40, beruf="Tierarzt", reception=False, nd_possible=True, nd_alone=True)  # type: ignore[arg-type]


def test_load_staff_csv_with_blank_hours_raises(tmp_path: Path) -> None:
    """Loading CSV with blank hours for a TFA raises StaffValidationError."""
    csv_file = tmp_path / "blank_hours.csv"
    csv_file.write_text(
        "name,identifier,adult,hours,beruf,reception,nd_possible,nd_alone\n"
        "Alice,A1,true,,TFA,true,true,true\n",
        encoding="utf-8",
    )
    with pytest.raises(StaffValidationError):
        load_staff_from_csv(csv_file)


def test_file_loader_passes_raw_beruf_to_model(tmp_path: Path) -> None:
    """file_loader passes raw beruf to model without duplicating role normalization (D1)."""
    csv_file = tmp_path / "staff.csv"
    csv_file.write_text(
        "Name,Kürzel,Alter,Stunden,Beruf,Anmeldung,Nacht_möglich,Nacht_alleine\n"
        "Dr. Vet,V1,true,,Vet,false,true,true\n"
        "Intern One,I1,true,40,Intern,false,true,true\n",
        encoding="utf-8",
    )
    raw_dict = load_staff_from_file(csv_file)
    assert raw_dict["V1"]["beruf"] == "Vet"
    assert raw_dict["I1"]["beruf"] == "Intern"

    # Loading via models creates valid Staff instances
    from app.scheduler.models import load_staff_from_file as load_models
    staff = load_models(csv_file)
    assert staff[0].beruf == Beruf.VET
    assert staff[1].beruf == Beruf.INTERN

