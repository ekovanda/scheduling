"""Unit tests for the schedule Excel and CSV export functionality."""

import io
from datetime import date

import openpyxl  # type: ignore[import-untyped]

from app.exporters.excel import export_schedule_to_csv, export_schedule_to_excel
from app.persistence.models import (
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    StaffMember,
)
from app.scheduler.file_loader import parse_previous_plan_xlsx
from app.scheduler.models import Beruf, ShiftType


def test_excel_and_csv_export_roundtrip() -> None:
    """Verify that generated Excel workbook matches required schema and parses back."""
    m1 = StaffMember(
        id="STAFF_01", identifier="MUE", name="Dr. Anna Müller", hours=40, beruf=Beruf.VET
    )
    m2 = StaffMember(id="STAFF_02", identifier="SCH", name="Schmidt", hours=40, beruf=Beruf.TFA)
    staff_map = {"STAFF_01": m1, "STAFF_02": m2}

    doc = QuarterScheduleDocument(
        quarter_key="2026-Q2",
        year=2026,
        quarter=2,
        state=ScheduleState.PUBLISHED,
        assignments=[
            ShiftAssignmentRecord(
                shift_date=date(2026, 4, 1),
                shift_type=ShiftType.NIGHT_WED_THU,
                planned_staff_id="MUE",
                actual_staff_id="MUE",
                is_paired=False,
            ),
            ShiftAssignmentRecord(
                shift_date=date(2026, 4, 4),
                shift_type=ShiftType.SATURDAY_10_22,
                planned_staff_id="SCH",
                actual_staff_id="SCH",
                is_paired=False,
                is_override=True,
                override_reason="Diensttausch",
            ),
        ],
    )

    # 1. Test CSV export
    csv_str = export_schedule_to_csv(doc)
    assert "N_Mi-Do" in csv_str
    assert "Sa_10-22" in csv_str
    assert "Tausch/Vertretung" in csv_str
    assert "Diensttausch" in csv_str

    # 2. Test Excel export
    excel_bytes = export_schedule_to_excel(doc, staff_map=staff_map)
    assert len(excel_bytes) > 0

    # Inspect workbook sheets with openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Nachtdienste" in wb.sheetnames
    assert "Wochenenddienste" in wb.sheetnames
    assert "Schichtverteilung" in wb.sheetnames

    # Check night sheet has 1 entry
    ws_nights = wb["Nachtdienste"]
    assert ws_nights.max_row == 2  # header + 1 row

    # Check weekend sheet has 1 entry
    ws_weekends = wb["Wochenenddienste"]
    assert ws_weekends.max_row == 2

    # 3. Verify parse_previous_plan_xlsx can read the generated file back directly!
    parsed_assignments = parse_previous_plan_xlsx(io.BytesIO(excel_bytes))
    assert len(parsed_assignments) == 2
    types = [a["shift_type"] for a in parsed_assignments]
    assert "N_Mi-Do" in types
    assert "Sa_10-22" in types
