#!/usr/bin/env python3
"""1-Click Migration & Seeding Script: Sync local clinic data into Google Cloud Firestore.

Usage:
    uv run python scripts/seed_firestore.py [--project PROJECT_ID] [--dry-run]
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.persistence.firestore_repository import FirestoreRepository
from app.persistence.repository import FileJsonRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Google Cloud Firestore from local baseline JSON records."
    )
    parser.add_argument(
        "--project",
        default=os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or "tierklinik-trillig",
        help="Google Cloud Project ID (default: tierklinik-trillig or $GCP_PROJECT)",
    )
    parser.add_argument(
        "--source-dir",
        default="data/db",
        help="Source directory containing flat JSON files (default: data/db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate records without writing to Firestore",
    )
    args = parser.parse_args()

    source_path = Path(args.source_dir)
    if not source_path.exists():
        print(f"Error: Source directory '{source_path}' does not exist.")
        sys.exit(1)

    file_repo = FileJsonRepository(base_dir=source_path)

    staff_members = file_repo.list_staff(active_only=False)
    # List all absences by inspecting raw directory
    absence_records = []
    for abs_file in sorted((source_path / "absences").glob("*.json")):
        rec = file_repo.get_absence(abs_file.stem)
        if rec:
            absence_records.append(rec)
    schedules = file_repo.list_schedules()
    preassigned = file_repo.list_preassigned()

    print("==========================================================")
    print(" Google Cloud Firestore Clinic Baseline Migration")
    print(f" Target Project : {args.project}")
    print(f" Source Path    : {source_path.resolve()}")
    print(f" Staff Members  : {len(staff_members)}")
    print(f" Absences       : {len(absence_records)}")
    print(f" Schedules      : {len(schedules)}")
    print(f" Pre-Assigned   : {len(preassigned)}")
    print(f" Mode           : {'DRY RUN (no writes)' if args.dry_run else 'LIVE UPLOAD'}")
    print("==========================================================")

    if args.dry_run:
        print("Dry run complete. All source records parsed successfully.")
        return

    print("Connecting to Firestore...")
    firestore_repo = FirestoreRepository(project=args.project)

    print("Uploading staff members...")
    for staff in staff_members:
        firestore_repo.save_staff(staff)
    print(f"✓ Uploaded {len(staff_members)} staff records.")

    print("Uploading absence ledger records...")
    for absence in absence_records:
        firestore_repo.save_absence(absence)
    print(f"✓ Uploaded {len(absence_records)} absence records.")

    print("Uploading quarterly schedules...")
    for schedule in schedules:
        firestore_repo.save_schedule(schedule)
    print(f"✓ Uploaded {len(schedules)} schedule documents.")

    print("Uploading pre-assigned shifts...")
    for pa in preassigned:
        firestore_repo.save_preassigned(pa)
    print(f"✓ Uploaded {len(preassigned)} pre-assigned shift records.")

    print("==========================================================")
    print("✓ Migration successfully completed!")
    print(f"Clinic Single Source of Truth (SSOT) is active on Firestore ({args.project}).")
    print("==========================================================")


if __name__ == "__main__":
    main()

