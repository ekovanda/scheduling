"""Pre-solve capacity analysis for Notdienst scheduling.

Provides a fast, pure-Python feasibility check that can be run before
invoking the CP-SAT solver.  Results surface potential infeasibility
causes (e.g. no viable 21-day blocks for a staff member) so the user
can fix input data before waiting for a solver timeout.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .models import (
    Beruf,
    PreAssignedShift,
    SchedulerConfig,
    ShiftType,
    Staff,
    Vacation,
    generate_quarter_shifts,
    get_pre_assigned_holiday_dates,
    get_staff_unavailable_dates,
)


class InfeasibilityCategory(str, Enum):
    """Categorization of scheduling infeasibility or configuration conflicts."""

    # Pre-assignment conflicts
    PREASSIGNED_SAME_DAY = "PREASSIGNED_SAME_DAY"
    PREASSIGNED_CONSECUTIVE_CAP = "PREASSIGNED_CONSECUTIVE_CAP"
    PREASSIGNED_WEEKEND_ISOLATION = "PREASSIGNED_WEEKEND_ISOLATION"
    PREASSIGNED_BLOCKED_WEEKDAY = "PREASSIGNED_BLOCKED_WEEKDAY"
    PREASSIGNED_ABSENCE_COLLISION = "PREASSIGNED_ABSENCE_COLLISION"
    PREASSIGNED_QUALIFICATION_MISMATCH = "PREASSIGNED_QUALIFICATION_MISMATCH"
    PREASSIGNED_SOLO_UNQUALIFIED = "PREASSIGNED_SOLO_UNQUALIFIED"
    PREASSIGNED_PAIRING_UNQUALIFIED = "PREASSIGNED_PAIRING_UNQUALIFIED"

    # Capacity & Structural conflicts
    CAPACITY_TFA_OPEN_NIGHTS = "CAPACITY_TFA_OPEN_NIGHTS"
    CAPACITY_TOTAL_NIGHTS = "CAPACITY_TOTAL_NIGHTS"
    CAPACITY_WEEKEND_ROLES = "CAPACITY_WEEKEND_ROLES"
    CAPACITY_VET_MIDWEEK = "CAPACITY_VET_MIDWEEK"
    CAPACITY_NO_VIABLE_BLOCKS = "CAPACITY_NO_VIABLE_BLOCKS"
    SOLVER_UNSATISFIABLE = "SOLVER_UNSATISFIABLE"


class DiagnosticSeverity(str, Enum):
    """Severity of a detected conflict or capacity issue."""

    ERROR = "ERROR"
    WARNING = "WARNING"


class InfeasibilityDiagnosticRecord(BaseModel):
    """Structured clinical diagnostic explaining an infeasibility or configuration clash."""

    category: InfeasibilityCategory
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    title: str
    message: str
    affected_staff_ids: list[str] = Field(default_factory=list)
    affected_dates: list[date] = Field(default_factory=list)
    remediation_hint: str


class FeasibilityReportRecord(BaseModel):
    """Aggregated report of pre-flight checks and feasibility analysis."""

    is_feasible: bool
    quarter_key: str
    diagnostics: list[InfeasibilityDiagnosticRecord] = Field(default_factory=list)
    blocking_error_count: int = 0
    warning_count: int = 0

GERMAN_WEEKDAYS = {
    1: "Montag",
    2: "Dienstag",
    3: "Mittwoch",
    4: "Donnerstag",
    5: "Freitag",
    6: "Samstag",
    7: "Sonntag",
}


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

    non_azubi_nd = [s for s in staff_list if s.nd_possible and s.beruf in (Beruf.TFA, Beruf.INTERN)]
    azubi_nd = [s for s in staff_list if s.nd_possible and s.beruf == Beruf.AZUBI]
    vet_nd = [s for s in staff_list if s.beruf == Beruf.VET and s.nd_possible]

    # Pre-compute per-staff block counts (used in Check A and Check B)
    per_staff_blocks: dict[str, tuple[int, int]] = {}
    for staff in non_azubi_nd + azubi_nd:
        gap = (
            config.intern_block_gap_days
            if staff.beruf == Beruf.INTERN
            else config.block_gap_days
        )
        n_blocks, avail = _count_viable_blocks(
            staff, vacations, pre_assigned, quarter_start, quarter_end,
            gap,
        )
        per_staff_blocks[staff.identifier] = (n_blocks, len(avail))

    # Pre-compute Vet relief capacity (Check F & Check A reduction)
    total_vet_blocks = 0
    total_vet_nights = 0
    vet_details: list[str] = []
    if vet_nd:
        months_in_quarter = sorted({(s.shift_date.year, s.shift_date.month) for s in night_shifts})
        for v in vet_nd:
            v_vacations = get_staff_unavailable_dates(vacations, v.identifier)
            avail_months = 0
            for yr, mo in months_in_quarter:
                has_slot = False
                for s in night_shifts:
                    if s.shift_date.year == yr and s.shift_date.month == mo:
                        d = s.shift_date
                        if d.weekday() == 1 and (d not in v_vacations) and ((d + timedelta(days=1)) not in v_vacations):
                            has_slot = True
                            break
                        elif d.weekday() == 2 and (d not in v_vacations) and ((d + timedelta(days=1)) not in v_vacations):
                            has_slot = True
                            break
                if has_slot:
                    avail_months += 1
            max_v_blocks = 2 if avail_months >= 2 else avail_months
            total_vet_blocks += max_v_blocks
            vet_details.append(f"{v.name}: bis zu {max_v_blocks} Blöcke ({max_v_blocks * 2} Nächte)")
        total_vet_nights = total_vet_blocks * 2

    checks: list[FeasibilityCheck] = []

    # -------------------------------------------------------------------------
    # Check A: Non-Azubi & TFA night supply
    # Open nights require 2 people (min 1 TFA); closed nights require 1-2 people.
    # Check 1: TFA block capacity >= open nights mandatory TFA slots.
    # Check 2: Combined (non-Azubi + Azubi) capacity >= total minimum night slots.
    # -------------------------------------------------------------------------
    open_nights_count = sum(1 for s in night_shifts if s.is_open_night())
    closed_nights_count = len(night_shifts) - open_nights_count
    min_tfa_demand_open = open_nights_count
    effective_closed_demand = max(0, closed_nights_count - total_vet_nights)
    total_slots_demand = (open_nights_count * 2) + effective_closed_demand

    tfa_nd = [s for s in non_azubi_nd if s.beruf == Beruf.TFA]
    total_tfa_coverage = sum(
        per_staff_blocks[s.identifier][0] * s.nd_min_consecutive
        for s in tfa_nd
    )
    total_all_coverage = sum(
        per_staff_blocks[s.identifier][0] * s.nd_min_consecutive
        for s in non_azubi_nd + azubi_nd
    )

    if total_tfa_coverage < min_tfa_demand_open:
        pct_tfa = total_tfa_coverage / min_tfa_demand_open if min_tfa_demand_open else 0
        status_a: Literal["ok", "warning", "error"] = "warning" if pct_tfa >= 0.7 else "error"
        checks.append(FeasibilityCheck(
            name="Non-Azubi Nacht-Kapazität",
            status=status_a,
            message=(
                f"TFA-Kapazität unzureichend für offene Nächte: ~{total_tfa_coverage} TFA-Slots "
                f"vs. {min_tfa_demand_open} benötigte Pflicht-Slots."
            ),
        ))
    elif total_all_coverage < total_slots_demand:
        pct_all = total_all_coverage / total_slots_demand if total_slots_demand else 0
        status_a = "warning" if pct_all >= 0.7 else "error"
        checks.append(FeasibilityCheck(
            name="Non-Azubi Nacht-Kapazität",
            status=status_a,
            message=(
                f"Gesamte Nacht-Kapazität knapp: ~{total_all_coverage} Slots "
                f"vs. mind. {total_slots_demand} benötigte Plätze "
                f"({open_nights_count} offene + {closed_nights_count} geschlossene Nächte)."
            ),
        ))
    else:
        checks.append(FeasibilityCheck(
            name="Non-Azubi Nacht-Kapazität",
            status="ok",
            message=(
                f"Nacht-Kapazität ausreichend: ~{total_all_coverage} Slots für mind. "
                f"{total_slots_demand} Schichtplätze (~{total_tfa_coverage} TFA-Slots für "
                f"{open_nights_count} offene Nächte)."
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
        intern_we_max = len(intern_nd) * 3
        checks.append(FeasibilityCheck(
            name="Intern Kapazität (Nächte & Wochenenden)",
            status="ok",
            message=(
                f"{len(intern_nd)} Intern(s): {intern_min_total}–{intern_max_total} "
                f"Nächte ({config.intern_min_nights}–{config.intern_max_nights}/Person) & "
                f"max. {intern_we_max} Wochenenden (≤1/Monat/Person)."
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

    # -------------------------------------------------------------------------
    # Check F: Vet-Nachtdienst-Entlastung
    # -------------------------------------------------------------------------
    if vet_nd:
        checks.append(FeasibilityCheck(
            name="Vet-Nachtdienst-Entlastung",
            status="ok",
            message=(
                f"{len(vet_nd)} Vet/Vets: bis zu {total_vet_blocks} Blöcke "
                f"({total_vet_nights} Nächte Entlastung) im Di–Do-Fenster (1x/2 Monate, 2er-Block)."
            ),
            details=vet_details,
        ))

    return CapacityReport(checks=checks)


def validate_pre_assigned_consistency(
    pre_assigned: list[PreAssignedShift],
    staff_list: list[Staff],
    vacations: list[Vacation],
    quarter_start: date,
    quarter_end: date,
) -> list[InfeasibilityDiagnosticRecord]:
    """Detect and explain hard constraint violations in pre-assigned shifts.

    Checks:
    1. Employee existence and basic role/qualification eligibility.
    2. Overlap with registered absences/vacations.
    3. Same-day double booking (more than 1 shift per day for same staff).
    4. Streak caps (nd_max_consecutive overrun on night shifts).
    5. Weekend shift isolation (<11h rest gap with adjacent shift).
    6. Blocked weekday exceptions (nd_exceptions).
    7. Solo night capability (nd_alone=False on closed nights).
    8. Paired night qualification (open nights require at least 1 TFA, max 1 Azubi).
    """
    diagnostics: list[InfeasibilityDiagnosticRecord] = []
    staff_by_id = {s.identifier: s for s in staff_list}

    def to_st(val: ShiftType | str) -> ShiftType | None:
        if isinstance(val, ShiftType):
            return val
        try:
            return ShiftType(val)
        except ValueError:
            return None

    by_staff: dict[str, list[PreAssignedShift]] = defaultdict(list)
    for pa in pre_assigned:
        if quarter_start <= pa.shift_date <= quarter_end:
            by_staff[pa.staff_identifier].append(pa)

    for ident, pa_list in by_staff.items():
        staff = staff_by_id.get(ident)
        if not staff:
            diagnostics.append(
                InfeasibilityDiagnosticRecord(
                    category=InfeasibilityCategory.PREASSIGNED_QUALIFICATION_MISMATCH,
                    severity=DiagnosticSeverity.ERROR,
                    title="Mitarbeiter nicht im Personalstamm",
                    message=f"Für das Kürzel '{ident}' existiert kein aktiver Mitarbeiter im Personalstamm.",
                    affected_staff_ids=[ident],
                    affected_dates=[pa.shift_date for pa in pa_list],
                    remediation_hint=f"Legen Sie '{ident}' im Personal-Manager an oder korrigieren Sie das Kürzel in den Vorbelegungen.",
                )
            )
            continue

        blocked_dates = _get_blocked_dates(staff, vacations, quarter_start, quarter_end)

        # 1. Check individual shift qualifications & absences & blocked weekdays
        for pa in pa_list:
            st = to_st(pa.shift_type)
            if st is None:
                continue

            # Absence collision
            if pa.shift_date in blocked_dates:
                diagnostics.append(
                    InfeasibilityDiagnosticRecord(
                        category=InfeasibilityCategory.PREASSIGNED_ABSENCE_COLLISION,
                        severity=DiagnosticSeverity.ERROR,
                        title="Vorbelegung kollidiert mit Abwesenheit / Urlaub",
                        message=(
                            f"{staff.name} ({staff.identifier}) hat am {pa.shift_date.strftime('%d.%m.%Y')} "
                            f"eine eingetragene Abwesenheit (Urlaub, Krankheit oder Geburtstag), "
                            f"wurde aber für {st.value} vorbelegt."
                        ),
                        affected_staff_ids=[staff.identifier],
                        affected_dates=[pa.shift_date],
                        remediation_hint=(
                            f"Löschen Sie die Vorbelegung von {staff.identifier} am {pa.shift_date.strftime('%d.%m.%Y')} "
                            f"oder passen Sie den Abwesenheitseintrag im Abwesenheits-Manager an."
                        ),
                    )
                )

            # Blocked weekday (nd_exceptions)
            if st.value.startswith("N_") and pa.shift_date.isoweekday() in staff.nd_exceptions:
                weekday_name = GERMAN_WEEKDAYS.get(pa.shift_date.isoweekday(), str(pa.shift_date.isoweekday()))
                diagnostics.append(
                    InfeasibilityDiagnosticRecord(
                        category=InfeasibilityCategory.PREASSIGNED_BLOCKED_WEEKDAY,
                        severity=DiagnosticSeverity.ERROR,
                        title="Vorbelegung an gesperrtem Wochentag",
                        message=(
                            f"{staff.name} ({staff.identifier}) ist am Wochentag {weekday_name} "
                            f"für Nachtdienste gesperrt (nd_exceptions), wurde jedoch für {st.value} "
                            f"am {pa.shift_date.strftime('%d.%m.%Y')} vorbelegt."
                        ),
                        affected_staff_ids=[staff.identifier],
                        affected_dates=[pa.shift_date],
                        remediation_hint="Entfernen Sie die Vorbelegung an diesem Tag oder passen Sie die gesperrten Wochentage in den Mitarbeiter-Stammdaten an.",
                    )
                )

            # Basic qualification / role check
            if not staff.can_work_shift(st, pa.shift_date):
                if not (st.value.startswith("N_") and pa.shift_date.isoweekday() in staff.nd_exceptions):
                    if not staff.adult and st.value.startswith("So_"):
                        msg = f"{staff.name} ({staff.identifier}) ist minderjährig und darf laut JArbSchG sonntags nicht für {st.value} am {pa.shift_date.strftime('%d.%m.%Y')} eingeteilt werden."
                        hint = "Weisen Sie den Sonntagsdienst einer volljährigen Fachkraft zu."
                    elif staff.beruf == Beruf.VET:
                        msg = f"Tierarzt {staff.name} ({staff.identifier}) kann nicht für {st.value} am {pa.shift_date.strftime('%d.%m.%Y')} eingeteilt werden (nur Di–Do Nächte zulässig)."
                        hint = "Tierarzt-Nachtdienste sind auf Dienstag bis Donnerstag beschränkt."
                    else:
                        msg = f"{staff.name} ({staff.identifier}, {staff.beruf.value}) erfüllt nicht die erforderliche Qualifikation für {st.value} am {pa.shift_date.strftime('%d.%m.%Y')}."
                        hint = "Prüfen Sie die Schichtanforderungen und weisen Sie eine passend qualifizierte Fachkraft zu."

                    diagnostics.append(
                        InfeasibilityDiagnosticRecord(
                            category=InfeasibilityCategory.PREASSIGNED_QUALIFICATION_MISMATCH,
                            severity=DiagnosticSeverity.ERROR,
                            title=f"Qualifikations-Konflikt für {st.value}",
                            message=msg,
                            affected_staff_ids=[staff.identifier],
                            affected_dates=[pa.shift_date],
                            remediation_hint=hint,
                        )
                    )

        # 2. Same-day double booking
        shifts_by_date: dict[date, list[PreAssignedShift]] = defaultdict(list)
        for pa in pa_list:
            shifts_by_date[pa.shift_date].append(pa)

        for d, d_shifts in shifts_by_date.items():
            if len(d_shifts) > 1:
                st_names = " und ".join(
                    st.value if (st := to_st(s.shift_type)) is not None else str(s.shift_type)
                    for s in d_shifts
                )
                diagnostics.append(
                    InfeasibilityDiagnosticRecord(
                        category=InfeasibilityCategory.PREASSIGNED_SAME_DAY,
                        severity=DiagnosticSeverity.ERROR,
                        title="Doppelbelegung am selben Kalendertag",
                        message=(
                            f"{staff.name} ({staff.identifier}) ist am {d.strftime('%d.%m.%Y')} "
                            f"für mehrere Schichten gleichzeitig vorbelegt: {st_names}. "
                            f"Pro Mitarbeiter ist maximal 1 Schicht pro Kalendertag erlaubt."
                        ),
                        affected_staff_ids=[staff.identifier],
                        affected_dates=[d],
                        remediation_hint="Entfernen Sie eine der Schichten am selben Tag oder teilen Sie den Dienst einer anderen Fachkraft zu.",
                    )
                )

        # 3. Streak caps (nd_max_consecutive)
        if staff.nd_max_consecutive is not None:
            night_dates = sorted({
                pa.shift_date for pa in pa_list
                if (st := to_st(pa.shift_type)) is not None and st.value.startswith("N_")
            })
            if night_dates:
                current_streak = [night_dates[0]]
                for i in range(1, len(night_dates)):
                    if night_dates[i] == current_streak[-1] + timedelta(days=1):
                        current_streak.append(night_dates[i])
                    else:
                        if len(current_streak) > staff.nd_max_consecutive:
                            diagnostics.append(
                                InfeasibilityDiagnosticRecord(
                                    category=InfeasibilityCategory.PREASSIGNED_CONSECUTIVE_CAP,
                                    severity=DiagnosticSeverity.ERROR,
                                    title="Höchstgrenze aufeinanderfolgender Nächte überschritten",
                                    message=(
                                        f"{staff.name} ({staff.identifier}) hat {len(current_streak)} Nächte in Folge "
                                        f"({current_streak[0].strftime('%d.%m.')} bis {current_streak[-1].strftime('%d.%m.%Y')}) "
                                        f"vorbelegt. Erlaubt sind maximal {staff.nd_max_consecutive} Nächte in Folge."
                                    ),
                                    affected_staff_ids=[staff.identifier],
                                    affected_dates=list(current_streak),
                                    remediation_hint=f"Kürzen Sie die Serie aufeinanderfolgender Nächte für {staff.name} auf maximal {staff.nd_max_consecutive} Nächte.",
                                )
                            )
                        current_streak = [night_dates[i]]
                if len(current_streak) > staff.nd_max_consecutive:
                    diagnostics.append(
                        InfeasibilityDiagnosticRecord(
                            category=InfeasibilityCategory.PREASSIGNED_CONSECUTIVE_CAP,
                            severity=DiagnosticSeverity.ERROR,
                            title="Höchstgrenze aufeinanderfolgender Nächte überschritten",
                            message=(
                                f"{staff.name} ({staff.identifier}) hat {len(current_streak)} Nächte in Folge "
                                f"({current_streak[0].strftime('%d.%m.')} bis {current_streak[-1].strftime('%d.%m.%Y')}) "
                                f"vorbelegt. Erlaubt sind maximal {staff.nd_max_consecutive} Nächte in Folge."
                            ),
                            affected_staff_ids=[staff.identifier],
                            affected_dates=list(current_streak),
                            remediation_hint=f"Kürzen Sie die Serie aufeinanderfolgender Nächte für {staff.name} auf maximal {staff.nd_max_consecutive} Nächte.",
                        )
                    )

        # 4. Weekend Shift Isolation (<11h rest gap with adjacent shift)
        we_shifts = [
            pa for pa in pa_list
            if (st := to_st(pa.shift_type)) is not None and st.value.startswith(("Sa_", "So_"))
        ]
        all_shift_dates = {pa.shift_date: pa for pa in pa_list}
        for we in we_shifts:
            we_st = to_st(we.shift_type)
            for adj_date in [we.shift_date - timedelta(days=1), we.shift_date + timedelta(days=1)]:
                if adj_date in all_shift_dates:
                    other = all_shift_dates[adj_date]
                    other_st = to_st(other.shift_type)
                    is_intern_pair = (
                        we_st == ShiftType.SATURDAY_INTERN
                        and other_st == ShiftType.SUNDAY_INTERN
                        and other.shift_date == we.shift_date + timedelta(days=1)
                    ) or (
                        we_st == ShiftType.SUNDAY_INTERN
                        and other_st == ShiftType.SATURDAY_INTERN
                        and other.shift_date == we.shift_date - timedelta(days=1)
                    )
                    if not is_intern_pair:
                        diagnostics.append(
                            InfeasibilityDiagnosticRecord(
                                category=InfeasibilityCategory.PREASSIGNED_WEEKEND_ISOLATION,
                                severity=DiagnosticSeverity.ERROR,
                                title="Verletzung der Wochenend-Isolation / 11h-Ruhezeit",
                                message=(
                                    f"{staff.name} ({staff.identifier}) ist für {we_st.value if we_st else we.shift_type} "
                                    f"am {we.shift_date.strftime('%d.%m.%Y')} und eine direkt angrenzende Schicht "
                                    f"{other_st.value if other_st else other.shift_type} am {other.shift_date.strftime('%d.%m.%Y')} "
                                    f"eingeteilt. Dies verletzt die gesetzliche Ruhezeit von 11 Stunden."
                                ),
                                affected_staff_ids=[staff.identifier],
                                affected_dates=[we.shift_date, other.shift_date],
                                remediation_hint="Legen Sie mindestens einen freien Tag zwischen Wochenenddienst und Nachtdienst.",
                            )
                        )

    # 5. Night Pairings & Solo Qualifications
    night_shifts_by_date: dict[date, list[PreAssignedShift]] = defaultdict(list)
    for pa in pre_assigned:
        if quarter_start <= pa.shift_date <= quarter_end:
            st = to_st(pa.shift_type)
            if st and st.value.startswith("N_"):
                night_shifts_by_date[pa.shift_date].append(pa)

    for d, d_nights in night_shifts_by_date.items():
        first_st = to_st(d_nights[0].shift_type)
        if not first_st:
            continue

        if first_st in (ShiftType.NIGHT_FRI_SAT, ShiftType.NIGHT_SAT_SUN, ShiftType.NIGHT_SUN_MON):
            if len(d_nights) == 2:
                s1 = staff_by_id.get(d_nights[0].staff_identifier)
                s2 = staff_by_id.get(d_nights[1].staff_identifier)
                if s1 and s2:
                    if s1.beruf != Beruf.TFA and s2.beruf != Beruf.TFA:
                        diagnostics.append(
                            InfeasibilityDiagnosticRecord(
                                category=InfeasibilityCategory.PREASSIGNED_PAIRING_UNQUALIFIED,
                                severity=DiagnosticSeverity.ERROR,
                                title="Fehlende TFA bei offener Wochenend-Nacht",
                                message=(
                                    f"Am {d.strftime('%d.%m.%Y')} (offene Nacht) sind {s1.name} ({s1.beruf.value}) "
                                    f"und {s2.name} ({s2.beruf.value}) eingeteilt. Offene Nächte erfordern zwingend "
                                    f"mindestens eine voll qualifizierte TFA."
                                ),
                                affected_staff_ids=[s1.identifier, s2.identifier],
                                affected_dates=[d],
                                remediation_hint="Ersetzen Sie eine der beiden Personen durch eine TFA.",
                            )
                        )
                    if s1.beruf == Beruf.AZUBI and s2.beruf == Beruf.AZUBI:
                        diagnostics.append(
                            InfeasibilityDiagnosticRecord(
                                category=InfeasibilityCategory.PREASSIGNED_PAIRING_UNQUALIFIED,
                                severity=DiagnosticSeverity.ERROR,
                                title="Unzulässiges Azubi-Doppel im Nachtdienst",
                                message=(
                                    f"Am {d.strftime('%d.%m.%Y')} sind zwei Auszubildende ({s1.name} und {s2.name}) "
                                    f"eingeteilt. Maximal ein Azubi darf pro Nacht Dienst haben."
                                ),
                                affected_staff_ids=[s1.identifier, s2.identifier],
                                affected_dates=[d],
                                remediation_hint="Teilen Sie mindestens eine erfahrene Fachkraft ein.",
                            )
                        )
        else:
            if len(d_nights) == 1:
                s = staff_by_id.get(d_nights[0].staff_identifier)
                if s and not s.nd_alone:
                    diagnostics.append(
                        InfeasibilityDiagnosticRecord(
                            category=InfeasibilityCategory.PREASSIGNED_SOLO_UNQUALIFIED,
                            severity=DiagnosticSeverity.ERROR,
                            title="Alleindienst ohne Berechtigung (nd_alone=False)",
                            message=(
                                f"{s.name} ({s.identifier}) ist am {d.strftime('%d.%m.%Y')} allein für "
                                f"{first_st.value} vorbelegt, besitzt jedoch keine Alleindienst-Berechtigung."
                            ),
                            affected_staff_ids=[s.identifier],
                            affected_dates=[d],
                            remediation_hint=f"Weisen Sie {s.name} eine begleitende Fachkraft zu oder besetzen Sie die Nacht mit einer alleindienstfähigen Fachkraft.",
                        )
                    )

    return diagnostics


def validate_capacity_and_coverage(
    staff_list: list[Staff],
    vacations: list[Vacation],
    pre_assigned: list[PreAssignedShift],
    quarter_start: date,
    quarter_end: date,
    config: SchedulerConfig,
) -> list[InfeasibilityDiagnosticRecord]:
    """Check macro-level team capacity against required shift volume."""
    report = analyze_capacity(
        staff_list=staff_list,
        vacations=vacations,
        pre_assigned=pre_assigned,
        quarter_start=quarter_start,
        config=config,
    )
    diagnostics: list[InfeasibilityDiagnosticRecord] = []

    for check in report.checks:
        if check.status == "ok":
            continue

        sev = DiagnosticSeverity.WARNING

        if check.name == "Non-Azubi Nacht-Kapazität":
            category = InfeasibilityCategory.CAPACITY_TFA_OPEN_NIGHTS
            title = "TFA-Kapazität unzureichend für offene Nächte"
            hint = "Erhöhen Sie die TFA-Verfügbarkeit oder prüfen Sie Urlaubseinträge der TFA-Mitarbeiter."
        elif check.name == "Wochenend-Abdeckung":
            category = InfeasibilityCategory.CAPACITY_WEEKEND_ROLES
            title = "Fehlende Qualifikationen für Wochenendschichten"
            hint = "Aktivieren Sie im Mitarbeiterstamm die benötigten Qualifikationen (z.B. Azubi für Sa_10-19, Anmeldung für Sa_10-21)."
        elif check.name == "Mitarbeiter ohne gültige Blöcke":
            category = InfeasibilityCategory.CAPACITY_NO_VIABLE_BLOCKS
            title = "Mitarbeiter ohne zusammenhängenden Nachtblock"
            hint = "Prüfen Sie urlaubsbedingte Unterbrechungen oder reduzieren Sie nd_min_consecutive."
        elif check.name == "Azubi Pairing-Kapazität":
            category = InfeasibilityCategory.PREASSIGNED_PAIRING_UNQUALIFIED
            title = "Azubi-Begleitung im Nachtdienst knapp"
            hint = "Stellen Sie sicher, dass genügend erfahrene TFAs für Nachtbegleitungen zur Verfügung stehen."
        else:
            category = InfeasibilityCategory.CAPACITY_TOTAL_NIGHTS
            title = check.name
            hint = "Überprüfen Sie Urlaube und Mitarbeiterverfügbarkeiten."

        detail_text = f" Details: {'; '.join(check.details)}" if check.details else ""
        diagnostics.append(
            InfeasibilityDiagnosticRecord(
                category=category,
                severity=sev,
                title=title,
                message=f"{check.message}{detail_text}",
                remediation_hint=hint,
            )
        )

    return diagnostics


def run_full_feasibility_check(
    staff_list: list[Staff],
    vacations: list[Vacation],
    pre_assigned: list[PreAssignedShift],
    quarter_start: date,
    quarter_end: date,
    config: SchedulerConfig,
    quarter_key: str = "",
) -> FeasibilityReportRecord:
    """Run both deterministic pre-flight checks and capacity analyses."""
    diagnostics: list[InfeasibilityDiagnosticRecord] = []

    # 1. Micro-level pre-assigned hard constraint consistency
    diagnostics.extend(
        validate_pre_assigned_consistency(
            pre_assigned=pre_assigned,
            staff_list=staff_list,
            vacations=vacations,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
        )
    )

    # 2. Macro-level structural capacity and role coverage
    diagnostics.extend(
        validate_capacity_and_coverage(
            staff_list=staff_list,
            vacations=vacations,
            pre_assigned=pre_assigned,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
            config=config,
        )
    )

    blocking = [d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR]
    warnings = [d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]

    return FeasibilityReportRecord(
        is_feasible=len(blocking) == 0,
        quarter_key=quarter_key,
        diagnostics=diagnostics,
        blocking_error_count=len(blocking),
        warning_count=len(warnings),
    )


def diagnose_structured_infeasibility(
    staff_list: list[Staff],
    vacations: list[Vacation],
    pre_assigned: list[PreAssignedShift],
    quarter_start: date,
    quarter_end: date,
    config: SchedulerConfig,
    unsatisfiable_strings: list[str] | None = None,
) -> list[InfeasibilityDiagnosticRecord]:
    """Produce rich diagnostic records after an INFEASIBLE CP-SAT solver run."""
    report = run_full_feasibility_check(
        staff_list=staff_list,
        vacations=vacations,
        pre_assigned=pre_assigned,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        config=config,
    )
    diagnostics = list(report.diagnostics)

    if not diagnostics:
        raw_msg = (
            "; ".join(unsatisfiable_strings)
            if unsatisfiable_strings
            else "Das CP-SAT-Modell ist mit den gewählten Randbedingungen unlösbar."
        )
        diagnostics.append(
            InfeasibilityDiagnosticRecord(
                category=InfeasibilityCategory.SOLVER_UNSATISFIABLE,
                severity=DiagnosticSeverity.ERROR,
                title="Komplexe Randbedingungs-Kollision (CP-SAT Unlösbar)",
                message=(
                    f"Der mathematische Solver konnte keine Belegung finden, die gleichzeitig alle "
                    f"Ruhezeiten (11h), Höchstnächte, Wochenend-Entkopplungen und Urlaubszeiten erfüllt. ({raw_msg})"
                ),
                remediation_hint=(
                    "Lockern Sie Urlaubszeiten, vergrößern Sie den Mitarbeiterpool, "
                    "oder prüfen Sie, ob feste Vorbelegungen an Feiertagen das Restproblem überbeschränken."
                ),
            )
        )

    return diagnostics
