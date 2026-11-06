"""Seed real clinic baseline data (staff, vacations, 2026-Q4 realized plan, 2027-Q1 baseline)."""

from datetime import date, datetime
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]

from app.persistence.models import (
    AbsenceRecord,
    AbsenceType,
    PreAssignedShiftRecord,
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    StaffMember,
)
from app.persistence.repository import FileJsonRepository
from app.scheduler.file_loader import parse_previous_plan_xlsx
from app.scheduler.models import ShiftType, load_pre_assigned_from_file, load_staff_from_file


def seed_clinic_baseline(data_dir: Path | str = "data/db") -> None:
    """Populate persistent datastore with real clinic records from data/2027-Q1/ or fallback."""
    repo = FileJsonRepository(data_dir)
    q1_dir = Path("data/2027-Q1")

    if not q1_dir.exists():
        print(f"Error: {q1_dir} directory not found.")
        return

    print("==========================================================")
    print(" Seeding 2027-Q1 Planning Baseline & Clinic History")
    print(f" Source Directory : {q1_dir.resolve()}")
    print(f" Target Datastore : {Path(data_dir).resolve()}")
    print("==========================================================")

    # -------------------------------------------------------------------------
    # 1. Staff Members (data/2027-Q1/MA_excel.xlsx)
    # -------------------------------------------------------------------------
    print("--- 1. Seeding Staff Members ---")
    staff_file = q1_dir / "MA_excel.xlsx"
    raw_staff = load_staff_from_file(staff_file)
    ident_to_id: dict[str, str] = {}

    for s in raw_staff:
        staff_id = s.identifier.lower()
        ident_to_id[s.identifier] = staff_id
        member = StaffMember.from_scheduler_staff(s, staff_id=staff_id, is_active=True)
        repo.save_staff(member)

    # Inactivate departed employees not present in new 2027-Q1 roster
    active_idents = {s.identifier.upper() for s in raw_staff}
    for existing in repo.list_staff(active_only=False):
        if existing.identifier.upper() not in active_idents and existing.is_active:
            existing.is_active = False
            repo.save_staff(existing)
            print(f"ℹ️ Marked departed staff member {existing.name} ({existing.identifier}) as inactive.")

    print(f"✅ Saved {len(raw_staff)} master staff members to database.")

    # -------------------------------------------------------------------------
    # 2. Absence Ledger (data/2027-Q1/Urlaube_excel.xlsx)
    # -------------------------------------------------------------------------
    print("--- 2. Seeding Absence Records ---")
    vac_file = q1_dir / "Urlaube_excel.xlsx"
    wb_vac = openpyxl.load_workbook(vac_file, data_only=True)
    absence_count = 0

    # Scan sheets covering 2027-Q1 and preceding quarters (Q4, Q3)
    target_sheets = [s for s in ("Urlaube Q1", "Urlaube Q4", "Urlaube Q3") if s in wb_vac.sheetnames]
    for sheet_name in target_sheets:
        ws = wb_vac[sheet_name]
        for r in range(2, ws.max_row + 1):
            raw_id = ws.cell(r, 1).value
            raw_start = ws.cell(r, 2).value
            raw_end = ws.cell(r, 3).value
            if not raw_id or not raw_start or not raw_end:
                continue

            ident = str(raw_id).strip()
            staff_id = ident_to_id.get(ident, ident.lower())

            # Validate date objects
            if isinstance(raw_start, (datetime, date)):
                start_d = raw_start.date() if isinstance(raw_start, datetime) else raw_start
            else:
                try:
                    start_d = datetime.strptime(str(raw_start).strip()[:10], "%Y-%m-%d").date()
                except ValueError:
                    start_d = datetime.strptime(str(raw_start).strip(), "%d.%m.%Y").date()

            if isinstance(raw_end, (datetime, date)):
                end_d = raw_end.date() if isinstance(raw_end, datetime) else raw_end
            else:
                try:
                    end_d = datetime.strptime(str(raw_end).strip()[:10], "%Y-%m-%d").date()
                except ValueError:
                    end_d = datetime.strptime(str(raw_end).strip(), "%d.%m.%Y").date()

            # Ensure start <= end
            if start_d > end_d:
                start_d, end_d = end_d, start_d

            absence_count += 1
            record = AbsenceRecord(
                id=f"abs-seed-{absence_count}",
                staff_id=staff_id,
                absence_type=AbsenceType.VACATION,
                start_date=start_d,
                end_date=end_d,
                note=f"Urlaub ({sheet_name})",
            )
            repo.save_absence(record)

    wb_vac.close()
    print(f"✅ Saved {absence_count} absence records to database across {target_sheets}.")

    # -------------------------------------------------------------------------
    # 3. Pre-Assigned Easter 2027 Shifts (data/2027-Q1/Feiertage_Excel.xlsx)
    # -------------------------------------------------------------------------
    print("--- 3. Seeding Pre-Assigned Holiday Shifts ---")
    hol_file = q1_dir / "Feiertage_Excel.xlsx"
    raw_pa = load_pre_assigned_from_file(hol_file)
    pa_count = 0

    for idx, pa in enumerate(raw_pa):
        staff_id = ident_to_id.get(pa.staff_identifier, pa.staff_identifier.lower())
        pa_record = PreAssignedShiftRecord(
            id=f"pa-seed-{idx + 1}",
            staff_id=staff_id,
            staff_identifier=pa.staff_identifier,
            shift_date=pa.shift_date,
            shift_type=pa.shift_type.value,
            is_holiday=True,
            note="Osterfeiertage 2027 Vorgabe",
        )
        repo.save_preassigned(pa_record)
        pa_count += 1

    print(f"✅ Saved {pa_count} pre-assigned holiday shifts to database.")

    # -------------------------------------------------------------------------
    # 4. 2026-Q4 Preceding Realized Plan (data/2027-Q1/Q4_Arbeitseinsätze1.xlsx)
    # -------------------------------------------------------------------------
    print("--- 4. Seeding 2026-Q4 Preceding Realized Plan ---")
    q4_file = q1_dir / "Q4_Arbeitseinsätze1.xlsx"
    raw_q4_assignments = parse_previous_plan_xlsx(q4_file)
    q4_records = []

    for a in raw_q4_assignments:
        staff_id = ident_to_id.get(a["staff_identifier"], a["staff_identifier"].lower())
        q4_records.append(
            ShiftAssignmentRecord(
                shift_date=a["shift_date"],
                shift_type=ShiftType(a["shift_type"]),
                planned_staff_id=staff_id,
                actual_staff_id=staff_id,
                is_paired=a.get("is_paired", False),
                is_override=False,
            )
        )

    q4_doc = QuarterScheduleDocument(
        quarter_key="2026-Q4",
        year=2026,
        quarter=4,
        state=ScheduleState.CLOSED,
        assignments=q4_records,
        solver_metrics={
            "num_shifts": len(q4_records),
            "status": "closed_realized",
            "source": "Q4_Arbeitseinsätze1.xlsx",
        },
    )
    repo.save_schedule(q4_doc)
    print(f"✅ Saved 2026-Q4 schedule ({len(q4_records)} shifts) in state CLOSED.")

    # -------------------------------------------------------------------------
    # 5. Initialize 2027-Q1 Planning Document
    # -------------------------------------------------------------------------
    print("--- 5. Initializing 2027-Q1 Baseline Schedule ---")
    q1_doc = QuarterScheduleDocument(
        quarter_key="2027-Q1",
        year=2027,
        quarter=1,
        state=ScheduleState.DRAFT,
        assignments=[],
        solver_metrics={"status": "initialized_ready_for_solve"},
    )
    repo.save_schedule(q1_doc)
    print("✅ Initialized 2027-Q1 quarterly schedule document in state DRAFT.")

    print("\n🎉 Seeding complete! Database is fully populated with 2027-Q1 baseline data.")


if __name__ == "__main__":
    seed_clinic_baseline()
