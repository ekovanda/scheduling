"""Pre-solve capacity analysis for Notdienst scheduling.

Provides a fast, pure-Python feasibility check that can be run before
invoking the CP-SAT solver.  Results surface potential infeasibility
causes (e.g. no viable 21-day blocks for a staff member) so the user
can fix input data before waiting for a solver timeout.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from .models import (
    Beruf,
    PreAssignedShift,
    SchedulerConfig,
    Staff,
    Vacation,
    generate_quarter_shifts,
    get_pre_assigned_holiday_dates,
    get_staff_unavailable_dates,
)


@dataclass
class FeasibilityCheck:
    """Single capacity check result."""

    name: str
    status: Literal["ok", "warning", "error"]
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class CapacityReport:
    """Aggregated result of all pre-solve capacity checks."""

    checks: list[FeasibilityCheck] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(c.status == "error" for c in self.checks)


def _get_blocked_dates(
    staff: Staff,
    vacations: list[Vacation],
    quarter_start: date,
    quarter_end: date,
) -> set[date]:
    """Return all dates a staff member cannot work in the given quarter."""
    blocked: set[date] = get_staff_unavailable_dates(vacations, staff.identifier)

    # Birthday counts as a vacation day
    for year in {quarter_start.year, quarter_end.year}:
        bd = staff.get_birthday_date(year)
        if bd is not None and quarter_start <= bd <= quarter_end:
            blocked.add(bd)

    # Block dates before available_from for new employees
    if staff.available_from is not None and staff.available_from > quarter_start:
        block_end = min(staff.available_from - timedelta(days=1), quarter_end)
        current = quarter_start
        while current <= block_end:
            blocked.add(current)
            current += timedelta(days=1)

    return blocked


def _count_viable_blocks(
    staff: Staff,
    vacations: list[Vacation],
    pre_assigned: list[PreAssignedShift],
    quarter_start: date,
    quarter_end: date,
    block_gap_days: int,
) -> tuple[int, list[date]]:
    """Count viable night-block opportunities for a night-capable staff member.

    Returns (num_blocks, available_night_dates).  A block is a run of at least
    nd_min_consecutive consecutive available dates (respecting nd_exceptions and
    all absence types).  The count is capped by the 21-day gap rule.

    Pre-assigned (holiday) dates are excluded from the "available" pool but each
    counts as its own separate block opportunity with a relaxed gap.
    """
    blocked = _get_blocked_dates(staff, vacations, quarter_start, quarter_end)

    # Collect pre-assigned dates for this staff member within the quarter
    pa_dates: set[date] = {
        pa.shift_date
        for pa in pre_assigned
        if pa.staff_identifier == staff.identifier
        and quarter_start <= pa.shift_date <= quarter_end
    }
    # Pre-assigned dates are not "freely available" — block them from the run analysis
    blocked_for_runs = blocked | pa_dates

    # Build list of freely available night dates (weekday filter via nd_exceptions)
    available: list[date] = []
    current = quarter_start
    while current <= quarter_end:
        if current.isoweekday() not in staff.nd_exceptions and current not in blocked_for_runs:
            available.append(current)
        current += timedelta(days=1)

    # Find consecutive runs of length >= nd_min_consecutive
    min_c = staff.nd_min_consecutive
    runs: list[list[date]] = []
    if available:
        current_run: list[date] = [available[0]]
        for i in range(1, len(available)):
            if (available[i] - available[i - 1]).days == 1:
                current_run.append(available[i])
            else:
                if len(current_run) >= min_c:
                    runs.append(current_run)
                current_run = [available[i]]
        if len(current_run) >= min_c:
            runs.append(current_run)

    # Greedily count blocks respecting the block_gap_days window.
    # Within each long run we may fit multiple block start positions, so we
    # walk through the run advancing by block_gap_days each time.
    viable_blocks = 0
    last_block_start: date | None = None
    for run in runs:
        pos = 0
        while pos + min_c <= len(run):
            candidate = run[pos]
            if last_block_start is None or (candidate - last_block_start).days >= block_gap_days:
                viable_blocks += 1
                last_block_start = candidate
                pos += block_gap_days
            else:
                gap_remaining = block_gap_days - (candidate - last_block_start).days
                pos += gap_remaining

    # Each pre-assigned date is its own (holiday-gap) block opportunity
    viable_blocks += len(pa_dates)

    return viable_blocks, available


def analyze_capacity(
    staff_list: list[Staff],
    vacations: list[Vacation],
    pre_assigned: list[PreAssignedShift],
    quarter_start: date,
    config: SchedulerConfig,
) -> CapacityReport:
    """Run all pre-solve capacity checks and return a structured report.

    This is pure Python (no CP-SAT) and finishes in milliseconds, making it
    suitable for rendering on every page load.
    """
    holiday_dates = get_pre_assigned_holiday_dates(pre_assigned)
    shifts = generate_quarter_shifts(quarter_start, holiday_dates=holiday_dates)
    quarter_end = max(s.shift_date for s in shifts) if shifts else quarter_start

    night_shifts = [s for s in shifts if s.is_night_shift()]
    total_nights = len(night_shifts)

    non_azubi_nd = [s for s in staff_list if s.nd_possible and s.beruf != Beruf.AZUBI]
    azubi_nd = [s for s in staff_list if s.nd_possible and s.beruf == Beruf.AZUBI]

    # Pre-compute per-staff block counts (used in Check A and Check B)
    per_staff_blocks: dict[str, tuple[int, int]] = {}
    for staff in non_azubi_nd + azubi_nd:
        n_blocks, avail = _count_viable_blocks(
            staff, vacations, pre_assigned, quarter_start, quarter_end,
            config.block_gap_days,
        )
        per_staff_blocks[staff.identifier] = (n_blocks, len(avail))

    checks: list[FeasibilityCheck] = []

    # -------------------------------------------------------------------------
    # Check A: Non-Azubi night supply
    # Each viable block covers approx. nd_min_consecutive nights.
    # Compare estimated total coverage to total_nights demand.
    # -------------------------------------------------------------------------
    total_non_azubi_coverage = sum(
        per_staff_blocks[s.identifier][0] * s.nd_min_consecutive
        for s in non_azubi_nd
    )
    if total_non_azubi_coverage < total_nights:
        pct = total_non_azubi_coverage / total_nights if total_nights else 0
        status_a: Literal["ok", "warning", "error"] = "warning" if pct >= 0.7 else "error"
        checks.append(FeasibilityCheck(
            name="Non-Azubi Nacht-Kapazität",
            status=status_a,
            message=(
                f"Geschätzte Kapazität ~{total_non_azubi_coverage} Nacht-Slots "
                f"vs. {total_nights} benötigte Nächte."
            ),
        ))
    else:
        checks.append(FeasibilityCheck(
            name="Non-Azubi Nacht-Kapazität",
            status="ok",
            message=(
                f"Nacht-Kapazität ausreichend: ~{total_non_azubi_coverage} "
                f"Slots für {total_nights} Nächte."
            ),
        ))

    # -------------------------------------------------------------------------
    # Check B: Per-staff viable block count
    # -------------------------------------------------------------------------
    zero_block_details: list[str] = []
    for staff in non_azubi_nd + azubi_nd:
        n_blocks, n_avail = per_staff_blocks[staff.identifier]
        if n_blocks == 0:
            zero_block_details.append(
                f"{staff.name} ({staff.beruf.value}) — "
                f"{n_avail} verfügbare Termine, aber kein gültiger "
                f"{staff.nd_min_consecutive}-Tage-Block möglich."
            )

    if zero_block_details:
        checks.append(FeasibilityCheck(
            name="Mitarbeiter ohne gültige Blöcke",
            status="warning",
            message=(
                f"{len(zero_block_details)} nachtfähige(r) Mitarbeiter "
                f"ohne gültigen Block nach Urlaub/Ausnahmen."
            ),
            details=zero_block_details,
        ))
    else:
        all_nd_count = len(non_azubi_nd) + len(azubi_nd)
        checks.append(FeasibilityCheck(
            name="Mitarbeiter ohne gültige Blöcke",
            status="ok",
            message=f"Alle {all_nd_count} nachtfähigen Mitarbeiter haben ≥1 gültigen Block.",
        ))

    # -------------------------------------------------------------------------
    # Check C: Weekend coverage by shift type
    # -------------------------------------------------------------------------
    tfa_staff = [s for s in staff_list if s.beruf == Beruf.TFA]
    azubi_staff = [s for s in staff_list if s.beruf == Beruf.AZUBI]
    adult_azubi = [s for s in azubi_staff if s.adult]
    reception_eligible = [
        s for s in staff_list
        if s.beruf == Beruf.TFA or (s.beruf == Beruf.AZUBI and s.reception)
    ]

    we_errors: list[str] = []
    if not azubi_staff:
        we_errors.append("Keine Azubis für Sa_10-19 (Azubidienst) vorhanden.")
    if not adult_azubi:
        we_errors.append("Keine volljährigen Azubis für So_8-20:30 vorhanden.")
    if not tfa_staff:
        we_errors.append("Keine TFAs für Sa_10-22 / So_8-20 / So_10-22 vorhanden.")
    if not reception_eligible:
        we_errors.append("Keine TFA/Azubi(Anmeldung) für Sa_10-21 vorhanden.")

    if we_errors:
        checks.append(FeasibilityCheck(
            name="Wochenend-Abdeckung",
            status="error",
            message="Fehlende Mitarbeiter für bestimmte Wochenend-Schichttypen.",
            details=we_errors,
        ))
    else:
        checks.append(FeasibilityCheck(
            name="Wochenend-Abdeckung",
            status="ok",
            message=(
                f"{len(tfa_staff)} TFAs, {len(azubi_staff)} Azubis "
                f"({len(adult_azubi)} volljährig), {len(reception_eligible)} Anmeldung-fähig."
            ),
        ))

    # -------------------------------------------------------------------------
    # Check D: Intern capacity
    # -------------------------------------------------------------------------
    intern_nd = [s for s in staff_list if s.beruf == Beruf.INTERN and s.nd_possible]
    if intern_nd:
        intern_max_total = len(intern_nd) * config.intern_max_nights
        intern_min_total = len(intern_nd) * config.intern_min_nights
        checks.append(FeasibilityCheck(
            name="Intern Nacht-Kapazität",
            status="ok",
            message=(
                f"{len(intern_nd)} Intern(s): {intern_min_total}–{intern_max_total} "
                f"Nächte gesamt ({config.intern_min_nights}–{config.intern_max_nights}/Person)."
            ),
        ))

    # -------------------------------------------------------------------------
    # Check E: Azubi pairing supply
    # -------------------------------------------------------------------------
    if azubi_nd:
        if len(non_azubi_nd) < len(azubi_nd):
            checks.append(FeasibilityCheck(
                name="Azubi Pairing-Kapazität",
                status="warning",
                message=(
                    f"{len(azubi_nd)} nachtfähige Azubis, aber nur "
                    f"{len(non_azubi_nd)} Non-Azubi Nacht-Mitarbeiter — "
                    f"Paarung könnte eng werden."
                ),
            ))
        else:
            checks.append(FeasibilityCheck(
                name="Azubi Pairing-Kapazität",
                status="ok",
                message=(
                    f"{len(non_azubi_nd)} Non-Azubi Nacht-Mitarbeiter für "
                    f"{len(azubi_nd)} nachtfähige Azubis verfügbar."
                ),
            ))

    return CapacityReport(checks=checks)
