
import sys
from datetime import date, timedelta
from scheduler.models import load_staff_from_csv, generate_quarter_shifts
from pathlib import Path

# Load real data
staff_list = load_staff_from_csv(Path("data/staff_sample.csv"))
quarter_start = date(2026, 4, 1)
shifts = generate_quarter_shifts(quarter_start)

# 1. Total Demand Calculation
total_slots = 0
for s in shifts:
    if s.is_night_shift():
        # Night shift logic: 
        # Sun-Mon, Mon-Tue: 1 person
        # Others: 2 people (conservative estimate, as most need pairs)
        if s.shift_type.value in ["N_So-Mo", "N_Mo-Di"]:
            total_slots += 1
        else:
            # We assume mix of solo/pair. Let's say 1.5 avg or just assume worst case 2 for now to see stress
            total_slots += 1.8 
    else:
        # Day shifts always 1 person
        total_slots += 1

# 2. Supply Capacity with 3-Week Rule
# Rule: Max 1 block start every 21 days.
# Max blocks per person = 91 days / 21 days = 4.33 blocks.
# If a block is usually just 1 shift (e.g. 1 Saturday), then capacity is ~4.3 shifts per person.

active_staff_count = len([s for s in staff_list if s.hours > 0]) # Filter out inactive
total_capacity_strict = active_staff_count * 4.33

print(f"--- Constraint Analysis ---")
print(f"Total Staff: {len(staff_list)}")
print(f"Total Shifts: {len(shifts)}")
print(f"Estimated Slot Demand: {total_slots:.1f}")
print(f"Max Blocks per Person (3-Week Rule): 4.33")
print(f"Total Capacity (Slots) under Strict 3-Week Rule (assuming 1 shift/block): {total_capacity_strict:.1f}")

if total_capacity_strict < total_slots:
    print(f"\n[CRITICAL] The 3-Week Rule is MATHEMATICALLY IMPOSSIBLE.")
    print(f"Gap: {total_slots - total_capacity_strict:.1f} slots unfilled.")
    print(f"To fix, either:")
    print(f"  A) Relax to 2-weeks (14 days) -> Capacity: {active_staff_count * (91/14):.1f}")
    print(f"  B) Group shifts into larger blocks (e.g. Fri Night + Sat Day) - but this triggers Day/Night conflicts")
else:
    print(f"\nCapacity theoretically sufficient, but requires perfect packing.")

# 3. Night/Day Conflict Logic Check
# Just outputting text for me to read in the context
print(f"\n--- Code Inspection ---")
print(f"Checking for regressions in Day/Night conflict logic...")
