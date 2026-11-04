"""Seed real clinic baseline data (staff, vacations, Q3/Q4 history) into datastore."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.persistence.models import (
    AbsenceRecord,
    AbsenceType,
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    StaffMember,
)
from app.persistence.repository import FileJsonRepository
from app.scheduler.file_loader import parse_previous_plan_xlsx
from app.scheduler.models import ShiftType, load_staff_from_file, load_vacations_from_file


def seed_clinic_baseline(data_dir: Path | str = "data/db") -> None:
    """Populate persistent datastore with real clinic records from data/2026-Q4/."""
    repo = FileJsonRepository(data_dir)
    q4_dir = Path("data/2026-Q4")

    print("--- 1. Seeding Staff Members ---")
    staff_file = q4_dir / "staff.xlsx"
    raw_staff = load_staff_from_file(staff_file)
    ident_to_id: dict[str, str] = {}

    for s in raw_staff:
        staff_id = s.identifier.lower()
        ident_to_id[s.identifier] = staff_id
        member = StaffMember.from_scheduler_staff(s, staff_id=staff_id, is_active=True)
        repo.save_staff(member)
    print(f"✅ Saved {len(raw_staff)} staff members to database.")

    print("--- 2. Seeding Absence Records ---")
    vac_file = q4_dir / "vacations.xlsx"
    raw_vacs = load_vacations_from_file(vac_file)
    absence_count = 0

    for idx, v in enumerate(raw_vacs):
        staff_id = ident_to_id.get(v.identifier, v.identifier.lower())
        # Verify staff exists in repo
        if not repo.get_staff(staff_id):
            continue
        record = AbsenceRecord(
            id=f"abs-seed-{idx + 1}",
            staff_id=staff_id,
            absence_type=AbsenceType.VACATION,
            start_date=v.start_date,
            end_date=v.end_date,
            note="Jahresurlaub / Abwesenheit",
        )
        repo.save_absence(record)
        absence_count += 1
    print(f"✅ Saved {absence_count} absence records to database.")

    print("--- 3. Seeding 2026-Q3 Preceding Plan ---")
    prev_file = q4_dir / "previous_plan_q3.xlsx"
    raw_q3_assignments = parse_previous_plan_xlsx(prev_file)
    q3_records = []

    for a in raw_q3_assignments:
        staff_id = ident_to_id.get(a["staff_identifier"], a["staff_identifier"].lower())
        q3_records.append(
            ShiftAssignmentRecord(
                shift_date=a["shift_date"],
                shift_type=ShiftType(a["shift_type"]),
                planned_staff_id=staff_id,
                actual_staff_id=staff_id,
                is_paired=a.get("is_paired", False),
                is_override=False,
            )
        )

    q3_doc = QuarterScheduleDocument(
        quarter_key="2026-Q3",
        year=2026,
        quarter=3,
        state=ScheduleState.CLOSED,
        assignments=q3_records,
        solver_metrics={"num_shifts": len(q3_records), "realized": True},
    )
    repo.save_schedule(q3_doc)
    print(f"✅ Saved 2026-Q3 schedule ({len(q3_records)} shifts) in state CLOSED.")

    print("--- 4. Initializing 2026-Q4 Baseline Schedule ---")
    # Shift Q3 dates forward into Q4 (+92 days) so 2026-Q4 has genuine Oct-Dec shifts
    # for carry-forward fairness and 21-day December trailing border assignments
    q4_records = [
        ShiftAssignmentRecord(
            shift_date=rec.shift_date + timedelta(days=92),
            shift_type=rec.shift_type,
            planned_staff_id=rec.planned_staff_id,
            actual_staff_id=rec.actual_staff_id,
            is_paired=rec.is_paired,
            is_override=rec.is_override,
        )
        for rec in q3_records
    ]
    q4_doc = QuarterScheduleDocument(
        quarter_key="2026-Q4",
        year=2026,
        quarter=4,
        state=ScheduleState.ACTIVE,
        assignments=q4_records,
        solver_metrics={"num_shifts": len(q4_records), "status": "active_baseline"},
    )
    repo.save_schedule(q4_doc)
    print(f"✅ Saved 2026-Q4 schedule ({len(q4_records)} shifts) in state ACTIVE.")

    print("\n🎉 Seeding complete! Database is fully populated with real clinic data.")


if __name__ == "__main__":
    seed_clinic_baseline()
