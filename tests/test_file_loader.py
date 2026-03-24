"""Tests for flexible file loading (CSV and XLSX)."""

import json
from datetime import date
from pathlib import Path

import pytest

from scheduler.file_loader import (
    ColumnMappingError,
    FileFormatError,
    load_file_to_dataframe,
    load_staff_from_file,
    load_vacations_from_file,
)


@pytest.fixture
def sample_staff_csv(tmp_path: Path) -> Path:
    """Create a sample staff CSV file with German column names."""
    csv_file = tmp_path / "staff.csv"
    csv_file.write_text(
        """Name,Kürzel,Alter,Stunden,Beruf,Anmeldung,Nacht_möglich,Nacht_alleine
Max Müller,MM,true,40,TFA,true,true,false
Lisa Schmidt,LS,true,20,Azubi,false,true,true
John Doe,JD,false,30,Intern,false,true,true
""",
        encoding="utf-8",
    )
    return csv_file


@pytest.fixture
def sample_staff_xlsx(tmp_path: Path) -> Path:
    """Create a sample staff XLSX file."""
    pytest.importorskip("openpyxl")
    import pandas as pd

    df = pd.DataFrame({
        "Name": ["Max Müller", "Lisa Schmidt"],
        "Identifier": ["MM", "LS"],
        "Adult": [True, True],
        "Hours": [40, 20],
        "Beruf": ["TFA", "Azubi"],
        "Reception": [True, False],
        "ND_Possible": [True, True],
        "ND_Alone": [False, True],
    })
    xlsx_file = tmp_path / "staff.xlsx"
    df.to_excel(xlsx_file, index=False)
    return xlsx_file


@pytest.fixture
def sample_vacation_csv(tmp_path: Path) -> Path:
    """Create a sample vacation CSV file."""
    csv_file = tmp_path / "vacations.csv"
    csv_file.write_text(
        """Mitarbeiter,Von,Bis
MM,2026-04-01,2026-04-05
LS,2026-05-10,2026-05-12
""",
        encoding="utf-8",
    )
    return csv_file


class TestFileLoading:
    """Test file format detection and loading."""

    def test_load_csv_file(self, sample_staff_csv: Path) -> None:
        """Test loading CSV file."""
        df = load_file_to_dataframe(sample_staff_csv)
        assert len(df) == 3
        assert "Name" in df.columns

    def test_load_xlsx_file(self, sample_staff_xlsx: Path) -> None:
        """Test loading XLSX file."""
        pytest.importorskip("openpyxl")
        df = load_file_to_dataframe(sample_staff_xlsx)
        assert len(df) == 2
        assert "Name" in df.columns

    def test_unsupported_format(self, tmp_path: Path) -> None:
        """Test that unsupported formats raise FileFormatError."""
        bad_file = tmp_path / "test.txt"
        bad_file.write_text("some content")
        with pytest.raises(FileFormatError):
            load_file_to_dataframe(bad_file)


class TestStaffLoading:
    """Test staff data loading with flexible column names."""

    def test_load_staff_from_csv_flexible_names(self, sample_staff_csv: Path) -> None:
        """Test loading staff from CSV with flexible column names."""
        staff_dict = load_staff_from_file(sample_staff_csv)
        assert len(staff_dict) == 3
        assert "MM" in staff_dict
        assert staff_dict["MM"]["name"] == "Max Müller"
        assert staff_dict["MM"]["beruf"] == "TFA"
        assert staff_dict["MM"]["adult"] is True
        assert staff_dict["MM"]["hours"] == 40

    def test_load_staff_from_xlsx(self, sample_staff_xlsx: Path) -> None:
        """Test loading staff from XLSX."""
        pytest.importorskip("openpyxl")
        staff_dict = load_staff_from_file(sample_staff_xlsx)
        assert len(staff_dict) == 2
        assert "MM" in staff_dict

    def test_missing_required_column(self, tmp_path: Path) -> None:
        """Test that missing required columns raise ColumnMappingError."""
        bad_csv = tmp_path / "bad_staff.csv"
        bad_csv.write_text("Name,Hours\nJohn,40\n", encoding="utf-8")
        with pytest.raises(ColumnMappingError):
            load_staff_from_file(bad_csv)

    def test_boolean_parsing(self, tmp_path: Path) -> None:
        """Test various boolean string formats."""
        csv_file = tmp_path / "bools.csv"
        csv_file.write_text(
            """Name,Kürzel,Adult,Hours,Beruf,Anmeldung,Nacht_möglich,Nacht_alleine
Max,MM,ja,40,TFA,yes,1,0
Lisa,LS,J,20,Azubi,true,TRUE,false
""",
            encoding="utf-8",
        )
        staff_dict = load_staff_from_file(csv_file)
        assert staff_dict["MM"]["adult"] is True
        assert staff_dict["MM"]["reception"] is True
        assert staff_dict["LS"]["adult"] is True

    def test_nd_exceptions_json_format(self, tmp_path: Path) -> None:
        """Test parsing nd_exceptions as JSON array."""
        csv_file = tmp_path / "staff_exceptions.csv"
        csv_file.write_text(
            """Name,Kürzel,Adult,Hours,Beruf,Anmeldung,Nacht_möglich,Nacht_alleine,Blockierte_Wochentage
Max,MM,true,40,TFA,true,true,false,"[1, 2, 3]"
""",
            encoding="utf-8",
        )
        staff_dict = load_staff_from_file(csv_file)
        assert staff_dict["MM"]["nd_exceptions"] == [1, 2, 3]

    def test_nd_exceptions_comma_separated(self, tmp_path: Path) -> None:
        """Test parsing nd_exceptions as comma-separated values."""
        csv_file = tmp_path / "staff_exceptions_csv.csv"
        csv_file.write_text(
            """Name,Kürzel,Adult,Hours,Beruf,Anmeldung,Nacht_möglich,Nacht_alleine,Blockierte_Wochentage
Lisa,LS,true,40,Azubi,false,true,true,"1, 2, 3"
""",
            encoding="utf-8",
        )
        staff_dict = load_staff_from_file(csv_file)
        assert staff_dict["LS"]["nd_exceptions"] == [1, 2, 3]


class TestVacationLoading:
    """Test vacation data loading with flexible column names and date formats."""

    def test_load_vacations_from_csv(self, sample_vacation_csv: Path) -> None:
        """Test loading vacations from CSV with flexible column names."""
        vacation_dict = load_vacations_from_file(sample_vacation_csv)
        assert len(vacation_dict) == 2
        assert "MM" in vacation_dict
        assert len(vacation_dict["MM"]) == 1
        assert vacation_dict["MM"][0]["start_date"] == date(2026, 4, 1)
        assert vacation_dict["MM"][0]["end_date"] == date(2026, 4, 5)

    def test_date_format_iso(self, tmp_path: Path) -> None:
        """Test ISO date format (YYYY-MM-DD)."""
        csv_file = tmp_path / "vacations_iso.csv"
        csv_file.write_text(
            """Identifier,Start Date,End Date
MM,2026-04-01,2026-04-05
""",
            encoding="utf-8",
        )
        vacation_dict = load_vacations_from_file(csv_file)
        assert vacation_dict["MM"][0]["start_date"] == date(2026, 4, 1)

    def test_date_format_german(self, tmp_path: Path) -> None:
        """Test German date format (DD.MM.YYYY)."""
        csv_file = tmp_path / "vacations_de.csv"
        csv_file.write_text(
            """Identifier,Von,Bis
LS,01.04.2026,05.04.2026
""",
            encoding="utf-8",
        )
        vacation_dict = load_vacations_from_file(csv_file)
        assert vacation_dict["LS"][0]["start_date"] == date(2026, 4, 1)

    def test_multiple_vacation_periods_per_person(self, tmp_path: Path) -> None:
        """Test multiple vacation periods for same person."""
        csv_file = tmp_path / "vacations_multi.csv"
        csv_file.write_text(
            """Identifier,Von,Bis
MM,2026-04-01,2026-04-05
MM,2026-06-01,2026-06-10
""",
            encoding="utf-8",
        )
        vacation_dict = load_vacations_from_file(csv_file)
        assert len(vacation_dict["MM"]) == 2

    def test_invalid_date_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid dates raise ValueError."""
        csv_file = tmp_path / "vacations_bad.csv"
        csv_file.write_text(
            """Identifier,Von,Bis
MM,2026-04-01,invalid
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Could not parse date"):
            load_vacations_from_file(csv_file)

    def test_end_date_before_start_date_raises_error(self, tmp_path: Path) -> None:
        """Test that end_date < start_date raises ValueError."""
        csv_file = tmp_path / "vacations_reversed.csv"
        csv_file.write_text(
            """Identifier,Von,Bis
MM,2026-04-05,2026-04-01
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Invalid date range"):
            load_vacations_from_file(csv_file)
