"""Streamlit app for Notdienst scheduling."""

import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import hashlib
import os
from release_info import APP_NAME, CURRENT_VERSION, RELEASES
from scheduler.models import (
    Beruf,
    PreAssignedShift,
    PreviousPlanContext,
    SchedulerConfig,
    ShiftType,
    Staff,
    Vacation,
    build_previous_context,
    build_previous_context_from_xlsx,
    calculate_available_days,
    load_pre_assigned_from_file,
    load_staff_from_file,
    load_vacations_from_file,
    validate_pre_assigned,
)
from scheduler.feasibility import analyze_capacity
from scheduler.solver import generate_schedule
from scheduler.validator import find_cross_quarter_block_gap_exceptions, validate_schedule

# Page config
st.set_page_config(page_title="Dienstplan Generator", page_icon="📅", layout="wide")


def page_about() -> None:
    """Show application information and the business-facing release history."""
    current_release = RELEASES[0]

    st.title(f"ℹ️ Über {APP_NAME}")
    st.write("Erstellt faire Quartalspläne für Nacht- und Wochenenddienste.")

    col_version, col_release_date = st.columns(2)
    with col_version:
        st.metric("Aktuelle Version", CURRENT_VERSION)
    with col_release_date:
        st.metric("Stand", current_release.date)

    st.markdown("---")
    st.markdown(f"## Neu in Version {current_release.version}")
    st.markdown(f"### {current_release.summary}")
    for highlight in current_release.highlights:
        st.markdown(f"- {highlight}")

    st.markdown("---")
    st.markdown("## Versionsverlauf")
    st.caption("Die neuesten Änderungen stehen oben. Öffnen Sie einen Eintrag für Details.")
    for release in RELEASES:
        with st.expander(
            f"Version {release.version} · {release.date} · {release.summary}",
            expanded=False,
        ):
            for highlight in release.highlights:
                st.markdown(f"- {highlight}")


def main() -> None:
    """Main app entry point."""
    # Simple authentication: checks hashed password in Streamlit secrets or env var
    def _get_stored_password_hash() -> str | None:
        # Prefer Streamlit secrets (deployed on Streamlit Cloud)
        try:
            pw = st.secrets.get("password_hash") if hasattr(st, "secrets") else None
        except Exception:
            pw = None
        if not pw:
            pw = os.environ.get("PASSWORD_HASH")
        return pw

    def _verify_password(input_pw: str) -> bool:
        stored = _get_stored_password_hash()
        if not stored:
            # No password configured: allow access but show an informational note
            return True
        h = hashlib.sha256(input_pw.encode("utf-8")).hexdigest()
        return h == stored

    # Check authentication status BEFORE showing any UI
    stored_hash = _get_stored_password_hash()
    
    # Initialize authentication state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # If password is configured and user is not authenticated, show ONLY login form
    if stored_hash and not st.session_state.authenticated:
        st.title("🔐 Dienstplan Generator - Login")
        st.markdown("---")
        pw = st.text_input("Passwort eingeben:", type="password", key="login_pw")
        if st.button("Anmelden", type="primary"):
            if _verify_password(pw):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Falsches Passwort. Bitte versuchen Sie es erneut.")
        return
    
    # If no password configured, show info message once
    if not stored_hash:
        st.sidebar.info("ℹ️ Kein Passwort konfiguriert. Setzen Sie `password_hash` in Streamlit Secrets für Passwortschutz.")
    
    # User is authenticated (or no password required) - show full app
    st.sidebar.title("📅 Dienstplan Generator")
    
    # Handle navigation from buttons (e.g., "Plan anzeigen" button on Plan erstellen page)
    nav_default_index = 0
    nav_options = [
        "Daten hochladen",
        "Personal",
        "Urlaub",
        "Regeln",
        "Plan erstellen",
        "Plan anzeigen",
        "Export",
        "Über diese App",
    ]
    if "nav_target" in st.session_state:
        target = st.session_state.pop("nav_target")
        if target in nav_options:
            nav_default_index = nav_options.index(target)

    page = st.sidebar.radio(
        "Navigation",
        nav_options,
        index=nav_default_index,
    )

    # Initialize session state
    if "staff_list" not in st.session_state:
        st.session_state.staff_list = None
    if "vacations" not in st.session_state:
        st.session_state.vacations = None
    if "schedule" not in st.session_state:
        st.session_state.schedule = None
    if "validation_result" not in st.session_state:
        st.session_state.validation_result = None
    if "previous_context" not in st.session_state:
        st.session_state.previous_context = None
    if "pre_assigned" not in st.session_state:
        st.session_state.pre_assigned = None

    # Route to pages
    if page == "Daten hochladen":
        page_daten_hochladen()
    elif page == "Personal":
        page_personal()
    elif page == "Urlaub":
        page_urlaub()
    elif page == "Regeln":
        page_regeln()
    elif page == "Plan erstellen":
        page_plan_erstellen()
    elif page == "Plan anzeigen":
        page_plan_anzeigen()
    elif page == "Export":
        page_export()
    elif page == "Über diese App":
        page_about()


def page_daten_hochladen() -> None:
    """Page: Upload all required data files."""
    st.title("📂 Daten hochladen")

    # ── 1. Personaldaten ──────────────────────────────────────────────────────
    st.markdown("### 👥 Personaldaten")
    uploaded_file = st.file_uploader(
        "CSV oder Excel mit Personalinformationen",
        type=["csv", "xlsx"],
        help="Erwartete Spalten: name, identifier, adult, hours, beruf, reception, "
             "nd_possible, nd_alone, nd_count, nd_exceptions",
    )
    if uploaded_file is not None:
        try:
            temp_path = Path("temp_staff." + uploaded_file.name.split(".")[-1])
            with temp_path.open("wb") as f:
                f.write(uploaded_file.getvalue())
            staff_list = load_staff_from_file(temp_path)
            st.session_state.staff_list = staff_list
            st.success(f"✅ {len(staff_list)} Mitarbeiter geladen")
            temp_path.unlink(missing_ok=True)
        except Exception as e:
            st.error(f"❌ {e}")
    elif st.session_state.staff_list:
        st.caption(f"Geladen: {len(st.session_state.staff_list)} Mitarbeiter")

    # ── 2. Urlaubsdaten ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏖️ Urlaub / Verfügbarkeit")
    vacation_file = st.file_uploader(
        "CSV oder Excel mit Urlaubsdaten (optional)",
        type=["csv", "xlsx"],
        key="vacation_upload",
        help="Erwartete Spalten: identifier, start_date, end_date",
    )
    if vacation_file is not None:
        try:
            temp_path = Path("temp_vacations." + vacation_file.name.split(".")[-1])
            with temp_path.open("wb") as f:
                f.write(vacation_file.getvalue())
            vacations = load_vacations_from_file(temp_path)
            st.session_state.vacations = vacations
            st.success(f"✅ {len(vacations)} Urlaubseinträge geladen")
            temp_path.unlink(missing_ok=True)
        except Exception as e:
            st.error(f"❌ {e}")
    elif st.session_state.vacations:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"Geladen: {len(st.session_state.vacations)} Urlaubseinträge")
        with col2:
            if st.button("🗑️ Entfernen", key="remove_vacations"):
                st.session_state.vacations = None
                st.rerun()

    # ── 3. Feiertagsdienste ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎄 Vorgegebene Dienste (optional)")
    holiday_file = st.file_uploader(
        "CSV oder Excel mit vorgegebenen Diensten",
        type=["csv", "xlsx"],
        key="holiday_upload",
        help="Spalten: Datum, Nachtdienst, Dienst 8-20, Dienst 10-22, Azubi 8-20:30",
    )
    if holiday_file is not None:
        try:
            temp_path = Path("temp_holidays." + holiday_file.name.split(".")[-1])
            with temp_path.open("wb") as f:
                f.write(holiday_file.getvalue())
            pre_assigned = load_pre_assigned_from_file(temp_path)
            st.session_state.pre_assigned = pre_assigned
            st.success(f"✅ {len(pre_assigned)} vorgegebene Dienste geladen")
            temp_path.unlink(missing_ok=True)
        except Exception as e:
            st.error(f"❌ {e}")
    elif st.session_state.pre_assigned:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"Geladen: {len(st.session_state.pre_assigned)} vorgegebene Dienste")
        with col2:
            if st.button("🗑️ Entfernen", key="remove_pre_assigned"):
                st.session_state.pre_assigned = None
                st.rerun()

    # ── 4. Vorheriger Plan ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Vorheriger Plan (optional)")
    if st.session_state.staff_list is None:
        st.warning("⚠️ Personaldaten zuerst laden, damit Carry-Forward-Deltas berechnet werden können.")
    context_file = st.file_uploader(
        "Arbeitseinsätze des vorherigen Quartals (xlsx)",
        type=["xlsx"],
        key="context_upload",
        help="Exportierte xlsx des Vorquartals. Spalten: Wochentag, Datum, Mitarbeiter, Schicht, Paarweise.",
    )
    if context_file is not None:
        if st.session_state.staff_list is None:
            st.error("❌ Personaldaten müssen zuerst geladen werden.")
        else:
            try:
                ctx = build_previous_context_from_xlsx(context_file, st.session_state.staff_list)
                st.session_state.previous_context = ctx
                st.success(
                    f"✅ Kontext geladen — {ctx.quarter_start.strftime('%d.%m.%Y')} bis "
                    f"{ctx.quarter_end.strftime('%d.%m.%Y')} "
                    f"({len(ctx.carry_forward)} Mitarbeiter)"
                )
            except Exception as e:
                st.error(f"❌ {e}")
    elif st.session_state.previous_context is not None:
        ctx = st.session_state.previous_context
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(
                f"Geladen: {ctx.quarter_start.strftime('%d.%m.%Y')} – "
                f"{ctx.quarter_end.strftime('%d.%m.%Y')} "
                f"({len(ctx.carry_forward)} Mitarbeiter)"
            )
        with col2:
            if st.button("🗑️ Entfernen", key="remove_context"):
                st.session_state.previous_context = None
                st.rerun()


def page_urlaub() -> None:
    """Page: View vacation calendar."""
    st.title("🏖️ Urlaub / Abwesenheit")
    
    if st.session_state.vacations is None or len(st.session_state.vacations) == 0:
        st.warning("⚠️ Keine Urlaubsdaten geladen. Bitte zuerst auf 'Laden / CSV' Urlaubsdaten hochladen.")
        return
    
    vacations: list[Vacation] = st.session_state.vacations
    staff_list: list[Staff] | None = st.session_state.staff_list
    
    # Create staff lookup for names
    staff_names = {}
    if staff_list:
        staff_names = {s.identifier: s.name for s in staff_list}
    
    # View selection
    view_type = st.radio(
        "Ansicht wählen",
        ["📅 Kalender (nach Datum)", "👤 Liste (nach Mitarbeiter)"],
        horizontal=True,
    )
    
    if view_type == "📅 Kalender (nach Datum)":
        _show_vacation_calendar(vacations, staff_names)
    else:
        _show_vacation_by_employee(vacations, staff_names)


def _show_vacation_calendar(vacations: list[Vacation], staff_names: dict[str, str]) -> None:
    """Display vacation data as a calendar view sorted by date."""
    # Find date range
    all_dates: set[date] = set()
    for v in vacations:
        current = v.start_date
        while current <= v.end_date:
            all_dates.add(current)
            current += timedelta(days=1)
    
    if not all_dates:
        st.info("Keine Urlaubstage gefunden.")
        return
    
    min_date = min(all_dates)
    max_date = max(all_dates)
    
    # Date range filter
    st.markdown("### Zeitraum filtern")
    col1, col2 = st.columns(2)
    with col1:
        filter_start = st.date_input("Von", value=min_date, min_value=min_date, max_value=max_date)
    with col2:
        filter_end = st.date_input("Bis", value=max_date, min_value=min_date, max_value=max_date)
    
    # Build calendar data: date -> list of absent employees
    calendar_data: dict[date, list[str]] = {}
    current = filter_start
    while current <= filter_end:
        absent = []
        for v in vacations:
            if v.start_date <= current <= v.end_date:
                name = staff_names.get(v.identifier, v.identifier)
                absent.append(name)
        if absent:
            calendar_data[current] = sorted(absent)
        current += timedelta(days=1)
    
    # Display as table
    st.markdown("### 📅 Abwesenheitskalender")
    st.caption("Zeigt alle Mitarbeiter, die an einem bestimmten Tag abwesend sind.")
    
    if not calendar_data:
        st.info("Keine Abwesenheiten im gewählten Zeitraum.")
        return
    
    rows = []
    for d in sorted(calendar_data.keys()):
        weekday = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
        rows.append({
            "Datum": d.strftime("%Y-%m-%d"),
            "Wochentag": weekday,
            "Abwesend": ", ".join(calendar_data[d]),
            "Anzahl": len(calendar_data[d]),
        })
    
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=500)
    
    # Summary statistics
    st.markdown("### 📊 Zusammenfassung")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tage mit Abwesenheit", len(calendar_data))
    with col2:
        max_absent = max(len(v) for v in calendar_data.values()) if calendar_data else 0
        st.metric("Max. gleichzeitig abwesend", max_absent)
    with col3:
        unique_employees = set()
        for absent_list in calendar_data.values():
            unique_employees.update(absent_list)
        st.metric("Mitarbeiter mit Urlaub", len(unique_employees))


def _show_vacation_by_employee(vacations: list[Vacation], staff_names: dict[str, str]) -> None:
    """Display vacation data grouped by employee."""
    # Group by employee
    by_employee: dict[str, list[Vacation]] = {}
    for v in vacations:
        if v.identifier not in by_employee:
            by_employee[v.identifier] = []
        by_employee[v.identifier].append(v)
    
    st.markdown("### 👤 Urlaub nach Mitarbeiter")
    
    rows = []
    for identifier, vac_list in sorted(by_employee.items()):
        name = staff_names.get(identifier, identifier)
        total_days = sum(v.duration_days() for v in vac_list)
        periods = []
        for v in sorted(vac_list, key=lambda x: x.start_date):
            if v.start_date == v.end_date:
                periods.append(v.start_date.strftime("%d.%m."))
            else:
                periods.append(f"{v.start_date.strftime('%d.%m.')}-{v.end_date.strftime('%d.%m.')}")
        
        rows.append({
            "Kürzel": identifier,
            "Name": name,
            "Urlaubstage": total_days,
            "Zeiträume": ", ".join(periods),
            "Anzahl Perioden": len(vac_list),
        })
    
    df = pd.DataFrame(rows)
    df = df.sort_values("Urlaubstage", ascending=False)
    st.dataframe(df, use_container_width=True, height=500)
    
    # Summary
    st.markdown("### 📊 Zusammenfassung")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Mitarbeiter mit Urlaub", len(by_employee))
    with col2:
        total = sum(sum(v.duration_days() for v in vl) for vl in by_employee.values())
        st.metric("Urlaubstage gesamt", total)
    with col3:
        avg = total / len(by_employee) if by_employee else 0
        st.metric("Ø Urlaubstage/Person", f"{avg:.1f}")


def page_feiertage() -> None:
    """Removed: content merged into page_personal tab."""
    pass


def page_personal() -> None:
    """Page: Staff overview, Feiertage review, and Vorheriger Plan review."""
    st.title("👥 Personal")

    tab_personal, tab_feiertage, tab_prev_plan = st.tabs(
        ["👥 Personal", "🎄 Feiertage", "📊 Vorheriger Plan"]
    )

    # ── Tab 1: Personal ────────────────────────────────────────────────────────
    with tab_personal:
        if st.session_state.staff_list is None:
            st.warning("⚠️ Bitte zuerst Personaldaten laden (Seite 'Daten hochladen')")
        else:
            staff_list: list[Staff] = st.session_state.staff_list

            st.markdown("### 🔍 Mitarbeiter suchen")
            search_query = st.text_input(
                "Name oder Kürzel eingeben",
                placeholder="z.B. 'Müller' oder 'MM'",
                help="Suche nach Name oder Identifier (Groß-/Kleinschreibung wird ignoriert)",
            )

            st.markdown("### Filter")
            col1, col2, col3 = st.columns(3)
            with col1:
                role_filter = st.multiselect(
                    "Beruf filtern", options=[b.value for b in Beruf], default=[b.value for b in Beruf]
                )
            with col2:
                adult_filter = st.selectbox("Alter", ["Alle", "Erwachsene", "Minderjährige"])
            with col3:
                nd_filter = st.selectbox("Nachtdienst", ["Alle", "ND möglich", "ND nicht möglich"])

            filtered = staff_list
            if search_query:
                query_lower = search_query.lower()
                filtered = [
                    s for s in filtered
                    if query_lower in s.name.lower() or query_lower in s.identifier.lower()
                ]
            if role_filter:
                filtered = [s for s in filtered if s.beruf.value in role_filter]
            if adult_filter == "Erwachsene":
                filtered = [s for s in filtered if s.adult]
            elif adult_filter == "Minderjährige":
                filtered = [s for s in filtered if not s.adult]
            if nd_filter == "ND möglich":
                filtered = [s for s in filtered if s.nd_possible]
            elif nd_filter == "ND nicht möglich":
                filtered = [s for s in filtered if not s.nd_possible]

            st.markdown(f"### Mitarbeiter ({len(filtered)} von {len(staff_list)})")
            df = pd.DataFrame([s.model_dump() for s in filtered])
            st.dataframe(df, width="content", height=600)

            st.markdown("---")
            st.markdown("### Statistik")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("TFA", sum(1 for s in staff_list if s.beruf == Beruf.TFA))
            with col2:
                st.metric("Azubi", sum(1 for s in staff_list if s.beruf == Beruf.AZUBI))
            with col3:
                st.metric("Intern", sum(1 for s in staff_list if s.beruf == Beruf.INTERN))
            with col4:
                st.metric("Gesamt", len(staff_list))

            st.markdown("---")
            st.markdown("### 🎂 Geburtstage")
            st.caption(
                "Mitarbeiter dürfen an ihrem Geburtstag **keine Schicht** eingeteilt werden "
                "(wird wie ein Urlaubstag behandelt)."
            )
            month_names = {
                1: "Januar", 2: "Februar", 3: "März", 4: "April",
                5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
                9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
            }
            month_filter_options = ["Alle Monate"] + list(month_names.values())
            selected_month_label = st.selectbox("Monat filtern", month_filter_options, index=0)
            selected_month: int | None = None
            if selected_month_label != "Alle Monate":
                selected_month = next(k for k, v in month_names.items() if v == selected_month_label)

            birthday_rows = []
            for s in staff_list:
                if s.birthday is None:
                    continue
                bmonth, bday = (int(p) for p in s.birthday.split("-"))
                if selected_month is not None and bmonth != selected_month:
                    continue
                birthday_rows.append({
                    "Name": s.name,
                    "Kürzel": s.identifier,
                    "Beruf": s.beruf.value,
                    "Geburtstag": f"{bday:02d}. {month_names[bmonth]}",
                    "MM-DD": s.birthday,
                })

            if birthday_rows:
                birthday_rows.sort(key=lambda r: r["MM-DD"])
                bd_df = pd.DataFrame(birthday_rows).drop(columns=["MM-DD"])
                st.dataframe(bd_df, use_container_width=True)
                st.caption(
                    f"{len(birthday_rows)} von {sum(1 for s in staff_list if s.birthday)} "
                    "Mitarbeitern mit eingetragenem Geburtstag."
                )
            else:
                st.info("Keine Geburtstage für den gewählten Filter gefunden.")

    # ── Tab 2: Feiertage ───────────────────────────────────────────────────────
    with tab_feiertage:
        pre_assigned: list[PreAssignedShift] | None = st.session_state.pre_assigned
        if pre_assigned is None or len(pre_assigned) == 0:
            st.info("ℹ️ Keine vorgegebenen Dienste geladen. Upload über 'Daten hochladen'.")
        else:
            if st.button("🗑️ Vorgegebene Dienste entfernen", key="remove_pa_tab"):
                st.session_state.pre_assigned = None
                st.rerun()

            tab_staff: list[Staff] | None = st.session_state.staff_list
            tab_vac: list[Vacation] | None = st.session_state.vacations
            if tab_staff:
                pa_warnings = validate_pre_assigned(pre_assigned, tab_staff, tab_vac)
                if pa_warnings:
                    st.error(
                        "**⚠️ Konflikte erkannt — bitte vor der Planung beheben:**\n\n"
                        + "\n".join(f"- {w}" for w in pa_warnings)
                    )
                else:
                    st.success("✅ Keine Konflikte mit Personal- oder Urlaubsdaten.")
            else:
                st.warning("⚠️ Personaldaten nicht geladen — Konfliktprüfung nicht möglich.")

            pa_staff_names: dict[str, str] = (
                {s.identifier: s.name for s in tab_staff} if tab_staff else {}
            )
            unique_dates = sorted({pa.shift_date for pa in pre_assigned})
            rows = []
            for d in unique_dates:
                weekday_str = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
                day_assignments = [pa for pa in pre_assigned if pa.shift_date == d]
                row: dict[str, str] = {"Datum": f"{d.strftime('%d.%m.%Y')} {weekday_str}"}
                for pa in day_assignments:
                    name_or_id = pa_staff_names.get(pa.staff_identifier, pa.staff_identifier)
                    col_label = pa.shift_type.value
                    if col_label in row:
                        row[col_label] += f" + {name_or_id}"
                    else:
                        row[col_label] = name_or_id
                rows.append(row)

            if rows:
                df_holidays = pd.DataFrame(rows).set_index("Datum").fillna("")
                st.dataframe(df_holidays, use_container_width=True)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Feiertage", len(unique_dates))
            with col2:
                st.metric("Zuordnungen gesamt", len(pre_assigned))

    # ── Tab 3: Vorheriger Plan ─────────────────────────────────────────────────
    with tab_prev_plan:
        ctx: PreviousPlanContext | None = st.session_state.previous_context
        if ctx is None:
            st.info(
                "ℹ️ Kein Vorquartal-Kontext geladen. "
                "Erster Planungslauf startet ohne Carry-Forward-Deltas. "
                "Upload über 'Daten hochladen'."
            )
        else:
            if st.button("🗑️ Kontext entfernen", key="remove_ctx_tab"):
                st.session_state.previous_context = None
                st.rerun()

            st.markdown(
                f"**{ctx.quarter_start.strftime('%d.%m.%Y')} – "
                f"{ctx.quarter_end.strftime('%d.%m.%Y')}**"
            )

            cf_df = pd.DataFrame([e.model_dump() for e in ctx.carry_forward])
            if cf_df.empty:
                st.warning("Keine Carry-Forward-Daten im Kontext.")
            else:
                group_cols = st.columns(3)
                for idx, (beruf_key, label, icon) in enumerate([
                    ("TFA", "TFA", "👩‍⚕️"),
                    ("Azubi", "Azubi", "🎓"),
                    ("Intern", "Intern", "🩺"),
                ]):
                    grp = cf_df[cf_df["beruf"] == beruf_key]
                    if grp.empty:
                        continue
                    with group_cols[idx]:
                        st.markdown(f"#### {icon} {label}")
                        st.metric("Mitarbeiter", len(grp))
                        st.metric("Ø Norm./40h", f"{grp['normalized_40h'].mean():.2f}")
                        st.metric(
                            "Spread",
                            f"{grp['carry_forward_delta'].max() - grp['carry_forward_delta'].min():.2f}",
                        )

                st.markdown("---")
                st.caption(
                    "**Δ > 0**: Mehr als Ø geleistet → weniger im nächsten Quartal.  "
                    "**Δ < 0**: Weniger als Ø geleistet → mehr im nächsten Quartal."
                )
                display_cols = [
                    "name", "identifier", "beruf", "hours",
                    "effective_nights", "weekend_shifts", "total_notdienst",
                    "normalized_40h", "group_mean_40h", "carry_forward_delta",
                ]
                display_names = {
                    "name": "Name", "identifier": "Kürzel", "beruf": "Beruf",
                    "hours": "Std.", "effective_nights": "Eff. Nächte",
                    "weekend_shifts": "WE", "total_notdienst": "Gesamt",
                    "normalized_40h": "Norm./40h", "group_mean_40h": "Ø Gruppe",
                    "carry_forward_delta": "Delta",
                }
                table_df = cf_df[display_cols].rename(columns=display_names)

                def _style_delta(val: float) -> str:
                    if abs(val) < 0.5:
                        return "background-color: #c8e6c9"
                    if abs(val) < 1.5:
                        return "background-color: #fff9c4"
                    return "background-color: #ffcdd2"

                for beruf_val in ["TFA", "Azubi", "Intern"]:
                    grp_t = table_df[table_df["Beruf"] == beruf_val]
                    if grp_t.empty:
                        continue
                    st.markdown(f"##### {beruf_val}")
                    styled = grp_t.style.map(_style_delta, subset=["Delta"])
                    st.dataframe(styled, use_container_width=True, height=min(400, 35 * len(grp_t) + 38))

            if ctx.trailing_assignments:
                st.markdown("---")
                st.markdown("### Grenzschichten (letzte 21 Tage)")
                trail_rows = []
                for ta in sorted(ctx.trailing_assignments, key=lambda t: t.shift_date):
                    trail_rows.append({
                        "Datum": ta.shift_date.strftime("%d.%m.%Y"),
                        "Schicht": ta.shift_type.value,
                        "Mitarbeiter": ta.staff_identifier,
                        "Paarweise": "Ja" if ta.is_paired else "Nein",
                    })
                st.dataframe(pd.DataFrame(trail_rows), use_container_width=True, height=300)


def page_regeln() -> None:
    """Page: Display constraint rules."""
    st.title("📋 Regeln & Constraints")

    st.markdown(
        "Der Solver unterscheidet zwischen **harten Constraints** (nie verletzbar) "
        "und **weichen Constraints** (Optimierungsziele). Klappt einen Abschnitt auf für Details."
    )

    # ── HARD CONSTRAINTS ────────────────────────────────────────────────────
    st.markdown("## 🔒 Harte Constraints")

    with st.expander("📅 Wochenend-Schichttypen & Berechtigungen"):
        st.markdown("""
| Schichttyp | Berechtigt |
|---|---|
| **Sa 10-19** (Azubidienst) | Nur Azubis |
| **Sa 10-21** (Anmeldung) | TFA **oder** Azubi mit `reception=True` |
| **Sa 10-22** (Rufbereitschaft) | Nur TFA |
| **So 8-20** | Nur TFA |
| **So 8-20:30** (Azubidienst) | Nur erwachsene Azubis (`adult=True`) |
| **So 10-22** (Rufbereitschaft) | Nur TFA |

**Feiertage** (Werktage, die als Feiertag markiert sind) erhalten dasselbe Schichtmuster wie ein Sonntag.

**Weitere Einschränkungen:**
- Minderjährige (`adult=False`) dürfen **keine** Sonntagsschicht übernehmen.
- Interns arbeiten **nie** am Wochenende.
- Max. **1 Schicht pro Person pro Tag** (kein Doppeleinsatz).
- **Wochenend-Isolation**: Jede WE-Schicht muss einzeln stehen — kein angrenzendes Schicht am Vor- oder Folgetag.
        """)

    with st.expander("🌙 Nachtdienste – Besetzung & Rollen"):
        st.markdown("""
**Reguläre Nächte** (Di→Mi bis Sa→So):
- 1–2 Personen, mind. 1 Nicht-Azubi (TFA oder Intern).
- Zwei Azubis dürfen **nie** gemeinsam Nachtdienst machen.
- Azubis müssen **immer** mit einem TFA oder Intern gepaart sein.
- `nd_alone=False` (Nicht-Azubi): muss **paarweise** arbeiten (mind. 2 Personen gesamt).
- `nd_alone=True` (Nicht-Azubi): arbeitet **komplett allein** — keine weitere Person auf derselben Nacht.

**Vet-Nächte** (So→Mo und Mo→Di — TA vor Ort):
- Genau **1 Nicht-Azubi** (TFA oder Intern).
- Optional darf **1 Azubi** hinzukommen (max. 1).
- `nd_alone`-Regeln gelten auf diesen Nächten **nicht**.

**Intern-Kontingent:**
- Interns müssen pro Quartal **6–9 Nächte** übernehmen (≈ 2–3 pro Monat).

**Effektive Nachtzählung** (für Fairness):
- Azubi: immer **1,0×** (auch wenn gepaart).
- TFA/Intern, allein: **1,0×** | gepaart: **0,5×** pro Person.
        """)

    with st.expander("⏱️ Zeitliche Regeln (Sperren & Abstände)"):
        st.markdown("""
**3-Wochen-Regel (Blockabstand):**
- Pro Person darf max. 1 zusammenhängender Schichtblock in einem rollierenden **21-Tage-Fenster** beginnen.
- *Ausnahme Feiertage*: Wurde ein Schichtblock durch einen vorab zugewiesenen Feiertag erzwungen, gilt ein entspanntes Fenster von nur **7 Tagen** (statt 21).
- Über Quartalsgrenzen hinweg wird die Regel weich erzwungen (Verletzungen sind stark bestraft, aber nicht absolut verboten).

**Nacht/Tag-Konflikt:**
- Kein Tagdienst (WE-Schicht) am **selben Tag** oder **Folgetag** nach einer Nachtschicht.

**nd_exceptions:**
- Keine Nachtzuweisung an Wochentagen, die in `nd_exceptions` hinterlegt sind (1 = Mo, …, 7 = So).

**Urlaub & Abwesenheit:**
- Urlaubstage (aus der Urlaubsliste) sperren **alle** Schichttypen.
- **🎂 Geburtstag**: Der Geburtstag (`birthday`-Feld, Format `MM-DD`) wird wie ein Urlaubstag behandelt — keine Schicht am Geburtstag.
- **Neueinstieg** (`available_from`): Mitarbeiter, die erst im Quartal anfangen, werden vor ihrem Startdatum vollständig gesperrt.

**Vorheriger Plan (Carry-Forward):**
- Die letzten 21 Tage des Vorquartals werden berücksichtigt, damit 3-Wochen-Regel, Mindestnächte und Nacht/Tag-Konflikt über Quartalsgrenzen korrekt greifen.
        """)

    with st.expander("🏥 Abteilungs-Constraint (OP / Station)"):
        st.markdown("""
Mitarbeiter mit `abteilung=op` oder `abteilung=station` unterliegen zusätzlichen Einschränkungen,
um Kapazitätsengpässe in Spezialgebieten zu verhindern:

1. **Gleiche Nacht**: Zwei Mitarbeiter aus derselben Abteilung dürfen **nicht** gemeinsam auf einer Nachtschicht eingesetzt werden.
2. **Aufeinanderfolgende Nächte**: Zwei Mitarbeiter aus derselben Abteilung dürfen an aufeinanderfolgenden Tagen (Tag N und Tag N+1) **nicht** Nacht machen.

Mitarbeiter mit `abteilung=other` sind von beiden Regeln **ausgenommen**.
        """)

    with st.expander("✅ Mindest-Teilnahme"):
        st.markdown("""
Damit niemand ausschließlich Wochenenddienste oder ausschließlich Nachtdienste sammelt:

- **Wochenend-Pflicht**: Alle TFA und Azubis müssen pro Quartal mind. **1 Wochenendschicht** ableisten.
- **Nacht-Pflicht**: Alle Mitarbeiter mit `nd_possible=True` müssen pro Quartal mind. **1 Nachtschicht** ableisten.

*Ausnahme Nacht-Pflicht*: Wenn die nach Urlaub und `nd_exceptions` verbleibenden Nachttermine zu wenige gültige aufeinanderfolgende Blöcke für `nd_min_consecutive` bieten (< 3 Blöcke), entfällt die Pflicht und der Solver verlässt sich stattdessen auf das Fairness-Ziel.

**`nd_max_consecutive` (Max. aufeinanderfolgende Nächte):**
Wenn ein Mitarbeiter einen Wert in diesem Feld hat, erzwingt der Solver diese Obergrenze als **hartes Limit** — keine Nachtfolge darf länger sein. Der Validierungs-Score gibt zusätzlich **100 Strafpunkte** pro Verstoß (für extern importierte Pläne).
        """)

    with st.expander("📋 Min. aufeinanderfolgende Nächte (`nd_min_consecutive`)"):
        st.markdown("""
| Rolle | Standard | Bedeutung |
|---|---|---|
| Azubi | 1 | Einzelnächte erlaubt (immer gepaart) |
| TFA / Intern | 2 | Mindestens 2 aufeinanderfolgende Nächte pro Block |
| Sonderfall (z. B. Anika) | 3 | Mindestens 3 aufeinanderfolgende Nächte pro Block |

Wenn ein Mitarbeiter eine Nacht antritt, muss der gesamte Block mindestens `nd_min_consecutive` lang sein.
        """)

    # ── SOFT CONSTRAINTS ────────────────────────────────────────────────────
    st.markdown("## 🎯 Weiche Constraints (Optimierungsziele)")

    with st.expander("⚖️ Faire Verteilung – Solver-Objektiv (CP-SAT)"):
        st.markdown("""
Der Solver minimiert die **maximale FTE-normierte Abweichung** innerhalb jeder Berufsgruppe (TFA, Azubi, Intern).

**FTE-Normierung:**
```
FTE-Wert = Gesamte_Notdienste × (40 / Wochenstunden) × (Quartalstage / Anwesenheitstage)
```
- Mitarbeiter mit 20 Std. sollen halb so viele Dienste wie 40-Std.-Kollegen haben.
- Urlaubsbereinigt: Wer 2 Wochen Urlaub hat, hat entsprechend weniger erwartet.

**Zwei Fairness-Ziele (beide minimiert):**
1. **Primär**: Spanne (Max − Min) der FTE-Werte innerhalb TFA / Azubi / Intern.
   - Hartes Limit: Spanne ≤ 1,5 FTE-Einheiten (wird verletzt, wenn kein besserer Plan machbar ist).
2. **Sekundär** (geringeres Gewicht): Spanne der *Nacht*-FTE-Werte innerhalb nachtfähiger TFA/Azubi — verhindert, dass jemand nur Wochenenddienste sammelt.

**Carry-Forward (Vorquartal):**
Wer im Vorquartal mehr als der Gruppendurchschnitt geleistet hat (`carry_forward_delta > 0`), bekommt einen Bonus-Offset, der seinen FTE-Wert im neuen Quartal nach oben verschiebt — der Solver gleicht so historische Ungleichheiten aus.
        """)

    with st.expander("📊 Validierungs-Bewertung (Post-Solve Score)"):
        st.markdown("""
Nach dem Lösen berechnet der Validator einen **Soft-Penalty-Score** (niedriger = besser).
Dieser Score ist unabhängig vom Solver-Objektiv und dient der Übersicht:

| Komponente | Formel |
|---|---|
| Abweichung vom proportionalen Ziel | Σ (Ist − Ziel)² pro Mitarbeiter |
| Gruppen-Ungleichheit | Standardabweichung × 10 pro Gruppe |
| `nd_max_consecutive`-Überschreitung | **100 Punkte** pro Verstoß |

*Hinweis*: Da der CP-SAT-Solver `nd_max_consecutive` bereits als hartes Limit durchsetzt,
treten die 100-Punkte-Strafen nur bei extern importierten oder manuell bearbeiteten Plänen auf.
        """)



def page_vorheriger_plan() -> None:
    """Removed: content merged into page_personal tab."""
    pass


def page_plan_erstellen() -> None:
    """Page: Generate schedule."""
    st.title("🔨 Plan erstellen")

    if st.session_state.staff_list is None:
        st.warning("⚠️ Bitte zuerst Personaldaten laden (Seite 'Daten hochladen')")
        return

    st.markdown("### Quartal auswählen")
    col1, col2 = st.columns(2)
    with col1:
        quarter: str | None = st.selectbox(
            "Quartal", ["Q1", "Q2", "Q3", "Q4"], index=None, placeholder="Quartal wählen..."
        )
    with col2:
        year: int | None = st.selectbox(
            "Jahr", list(range(2026, 2031)), index=None, placeholder="Jahr wählen..."
        )

    if quarter is None or year is None:
        st.warning("⚠️ Bitte Quartal und Jahr auswählen, um fortzufahren.")
        return

    # Calculate quarter start
    quarter_starts = {
        "Q1": date(year, 1, 1),
        "Q2": date(year, 4, 1),
        "Q3": date(year, 7, 1),
        "Q4": date(year, 10, 1),
    }
    quarter_start = quarter_starts[quarter]

    st.info(f"📅 Zeitraum: {quarter_start.strftime('%d.%m.%Y')} - ca. 91 Tage")

    vacations = st.session_state.vacations or []
    pre_assigned: list[PreAssignedShift] = st.session_state.pre_assigned or []
    previous_context: PreviousPlanContext | None = st.session_state.previous_context

    # Solver parameters
    st.markdown("---")
    st.markdown("### Solver-Einstellungen")

    solve_mode = st.radio(
        "Berechnungstiefe",
        options=["Schnell (~1 Min.)", "Gründlich (~10 Min.)"],
        index=0,
        horizontal=True,
        help=(
            "Schnell: 60 Sekunden Zeitlimit — gut für erste Ergebnisse.\n"
            "Gründlich: 600 Sekunden — mehr Zeit für den Solver, die Fairness weiter zu optimieren.\n"
            "Der Solver kann auch früher abbrechen, sobald die optimale Lösung bewiesen ist."
        ),
    )
    max_solve_time_seconds = 60 if solve_mode == "Schnell (~1 Min.)" else 600

    with st.expander("⚙️ Erweiterte Einstellungen", expanded=False):
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            intern_min_nights = st.number_input(
                "Intern Min. Nächte", min_value=1, max_value=20, value=6, step=1,
                help="Mindestnächte pro Intern-Mitarbeiter pro Quartal.",
            )
            intern_max_nights = st.number_input(
                "Intern Max. Nächte", min_value=1, max_value=20, value=9, step=1,
                help="Maximalnächte pro Intern-Mitarbeiter pro Quartal.",
            )
            block_gap_days = st.number_input(
                "Block-Abstand (Tage)", min_value=7, max_value=42, value=21, step=1,
                help="Mindestabstand zwischen zwei Nacht-Blocks desselben Mitarbeiters.",
            )
        with col_cfg2:
            holiday_gap_days = st.number_input(
                "Feiertag-Abstand (Tage)", min_value=1, max_value=21, value=7, step=1,
                help="Verkürzter Mindestabstand nach einem Feiertagsdienst.",
            )
            random_seed_val = st.number_input(
                "Seed", min_value=0, max_value=9999, value=42, step=1,
                help="Gleicher Seed ergibt bei gleichen Daten denselben Plan.",
            )
        scheduler_config = SchedulerConfig(
            intern_min_nights=int(intern_min_nights),
            intern_max_nights=int(intern_max_nights),
            block_gap_days=int(block_gap_days),
            holiday_gap_days=int(holiday_gap_days),
        )
        st.session_state["scheduler_config"] = scheduler_config

    # Pre-solve capacity analysis
    st.markdown("---")
    st.markdown("### Kapazitätsanalyse")
    with st.spinner("Analysiere Kapazität..."):
        _cap_report = analyze_capacity(
            st.session_state.staff_list,
            vacations,
            pre_assigned,
            quarter_start,
            scheduler_config,
        )
    for _chk in _cap_report.checks:
        if _chk.status == "ok":
            st.success(f"✅ **{_chk.name}**: {_chk.message}")
        elif _chk.status == "warning":
            st.warning(f"⚠️ **{_chk.name}**: {_chk.message}")
            for _d in _chk.details:
                st.caption(f"  ↳ {_d}")
        else:
            st.error(f"❌ **{_chk.name}**: {_chk.message}")
            for _d in _chk.details:
                st.caption(f"  ↳ {_d}")
    # Generate button
    st.markdown("---")
    if st.button("🚀 Plan generieren", type="primary"):
        with st.spinner(f"⏳ Generiere Dienstplan mit CP-SAT (max. {max_solve_time_seconds}s)..."):
            try:
                staff_list: list[Staff] = st.session_state.staff_list
                _cfg = st.session_state.get("scheduler_config") or SchedulerConfig()
                result = generate_schedule(
                    staff_list,
                    quarter_start,
                    vacations=vacations,
                    max_solve_time_seconds=max_solve_time_seconds,
                    random_seed=int(random_seed_val),
                    previous_context=previous_context,
                    pre_assigned=pre_assigned,
                    config=_cfg,
                )

                if result.success:
                    best_schedule = result.get_best_schedule()
                    st.session_state.schedule = best_schedule

                    # Validate
                    validation = validate_schedule(best_schedule, staff_list)
                    st.session_state.validation_result = validation

                    st.success(
                        f"✅ Dienstplan erfolgreich erstellt! ({len(best_schedule.assignments)} Zuweisungen)"
                    )

                    # Convergence log
                    with st.expander("📈 Solver-Verlauf", expanded=False):
                        if result.convergence_log:
                            import matplotlib.pyplot as plt

                            log_df = pd.DataFrame(result.convergence_log)
                            # Drop the initial chaotic phase — only show solutions found after 5s
                            log_df = log_df[log_df["wall_time"] >= 5.0]

                            if log_df.empty:
                                st.info("Alle Lösungen wurden in den ersten 5 Sekunden gefunden.")
                            else:
                                times = log_df["wall_time"].tolist()
                                objectives = log_df["objective"].tolist()
                                max_time = max(times)

                                fig, ax = plt.subplots(figsize=(8, 4))
                                ax.plot(times, objectives, marker="o", linewidth=2,
                                        color="#5c6bc0", markersize=5)
                                ax.set_xlabel("Zeit (s)")
                                ax.set_ylabel("Lösungsqualität\n(niedrigere Werte = besser)")
                                ax.set_xticks(range(0, int(max_time) + 10, 10))
                                ax.yaxis.set_ticklabels([])
                                ax.grid(True, linestyle="--", alpha=0.5)
                                plt.tight_layout()
                                st.pyplot(fig)
                                plt.close(fig)
                            st.caption("Jeder Punkt zeigt eine verbesserte Lösung. Niedrigere Werte sind besser.")
                        else:
                            st.info("Lösung auf Anhieb optimal — kein iterativer Verlauf verfügbar.")

                else:
                    st.error("❌ Keine gültige Lösung gefunden!")
                    st.markdown("### Verletzungen der Hard Constraints:")
                    for constraint in result.unsatisfiable_constraints:
                        if constraint.startswith("  →"):
                            st.caption(constraint)
                        elif "warning" in constraint.lower() or "eng" in constraint.lower():
                            st.warning(f"⚠️ {constraint}")
                        else:
                            st.error(f"❌ {constraint}")

            except Exception as e:
                st.error(f"❌ Fehler beim Generieren: {e}")
                st.exception(e)

    # Current status + navigation (score persists here via session_state)
    st.markdown("---")
    if st.session_state.schedule:
        if st.session_state.validation_result:
            _v = st.session_state.validation_result
            _n_hard = len(_v.hard_violations)
            col_score, col_nav = st.columns([1, 1])
            with col_score:
                st.metric(
                    "Soft Penalty Score",
                    f"{_v.soft_penalty:.2f}",
                    help=(
                        "Bewertet Fairness und Regelkonformität. Niedriger = besser. "
                        "Aufschlüsselung im Tab 'Plan anzeigen → Fairness & Statistik'."
                    ),
                )
                if _n_hard == 0:
                    st.caption("✅ Keine harten Regelverstöße")
                else:
                    st.caption(f"⚠️ {_n_hard} harte Regelverstöße")
            with col_nav:
                st.success("✅ Plan vorhanden")
                if st.button("📅 Plan anzeigen →", type="primary"):
                    st.session_state.nav_target = "Plan anzeigen"
                    st.rerun()
        else:
            st.success("✅ Plan vorhanden")
            if st.button("📅 Plan anzeigen →", type="primary"):
                st.session_state.nav_target = "Plan anzeigen"
                st.rerun()
    else:
        st.info("ℹ️ Noch kein Plan generiert")


def page_plan_anzeigen() -> None:
    """Page: One-stop shop for viewing, analyzing and validating the schedule."""
    st.title("📅 Dienstplan Übersicht")

    if st.session_state.schedule is None:
        st.warning("⚠️ Bitte zuerst einen Plan erstellen (Seite 'Plan erstellen')")
        return

    schedule = st.session_state.schedule
    staff_list: list[Staff] = st.session_state.staff_list
    validation_result = st.session_state.validation_result
    boundary_exceptions = find_cross_quarter_block_gap_exceptions(
        schedule,
        st.session_state.previous_context,
        st.session_state.get("scheduler_config") or SchedulerConfig(),
    )
    boundary_exception_dates = {
        (exception.staff_identifier, exception.current_block_start)
        for exception in boundary_exceptions
    }

    # Tabs for different views
    tab_calendar, tab_stats, tab_validation = st.tabs(
        ["📆 Kalender", "📊 Fairness & Statistik", "✅ Validierung"]
    )

    # --- TAB 1: CALENDAR VIEW ---
    with tab_calendar:
        st.markdown("### Kompaktansicht")
        
        # Toggle between identifier and full name display
        show_names = st.toggle(
            "Volle Namen anzeigen",
            value=False,
            help="Umschalten zwischen Kürzeln (z.B. 'MM') und vollen Namen (z.B. 'Max Müller')",
        )
        
        # Build lookup map: identifier -> name
        id_to_name = {s.identifier: s.name for s in staff_list}
        
        # Night shift types (one per day)
        NIGHT_SHIFTS = frozenset({
            ShiftType.NIGHT_MON_TUE,
            ShiftType.NIGHT_TUE_WED,
            ShiftType.NIGHT_WED_THU,
            ShiftType.NIGHT_THU_FRI,
            ShiftType.NIGHT_FRI_SAT,
            ShiftType.NIGHT_SAT_SUN,
            ShiftType.NIGHT_SUN_MON,
        })

        # Column labels
        NIGHT_COL = "🌙 Nacht"
        WE_COLS = [
            (ShiftType.SATURDAY_10_19, "☀️ Sa 10-19: Azubidienst"),
            (ShiftType.SATURDAY_10_21, "☀️ Sa 10-21: Anmeldung/Ruf"),
            (ShiftType.SATURDAY_10_22, "☀️ Sa 10-22: Rufbereitschaft"),
            (ShiftType.SUNDAY_8_20, "☀️ So 08-20: Dienst"),
            (ShiftType.SUNDAY_10_22, "☀️ So 10-22: Rufbereitschaft"),
            (ShiftType.SUNDAY_8_2030, "☀️ So 08-20:30: Azubi/Ruf"),
        ]

        # Map (Date, Shift) -> [Staff1, Staff2]
        shift_map: dict[tuple, list[str]] = {}
        # Track which (Date, ShiftType) has at least one pre-assigned entry
        pre_assigned_cells: set[tuple] = set()
        boundary_exception_cells: set[tuple] = set()
        unique_dates = sorted({a.shift.shift_date for a in schedule.assignments})

        for assignment in schedule.assignments:
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            if key not in shift_map:
                shift_map[key] = []
            display_value = (
                id_to_name.get(assignment.staff_identifier, assignment.staff_identifier)
                if show_names
                else assignment.staff_identifier
            )
            shift_map[key].append(display_value)
            if assignment.is_pre_assigned:
                pre_assigned_cells.add(key)
            if (assignment.staff_identifier, assignment.shift.shift_date) in boundary_exception_dates:
                boundary_exception_cells.add(key)

        # Build rows: Date | 🌙 Nacht | 6× ☀️ Weekend
        all_cols = [NIGHT_COL] + [label for _, label in WE_COLS]
        calendar_rows = []
        # Track pre-assigned per row for cell-level styling
        pre_assigned_flags: list[dict[str, bool]] = []
        boundary_exception_flags: list[dict[str, bool]] = []
        for d in unique_dates:
            weekday_str = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
            row: dict[str, str] = {"Datum": f"{d.strftime('%d.%m.')} {weekday_str}"}
            flags: dict[str, bool] = {}
            exception_flags: dict[str, bool] = {}

            # Single night column: find the night shift for this date
            for ns in NIGHT_SHIFTS:
                staff_ids = shift_map.get((d, ns), [])
                if staff_ids:
                    warning_icon = " ⚠️" if (d, ns) in boundary_exception_cells else ""
                    row[NIGHT_COL] = " + ".join(staff_ids) + warning_icon
                    flags[NIGHT_COL] = (d, ns) in pre_assigned_cells
                    exception_flags[NIGHT_COL] = (d, ns) in boundary_exception_cells
                    break

            # Weekend columns
            for s_type, col_label in WE_COLS:
                staff_ids = shift_map.get((d, s_type), [])
                if staff_ids:
                    warning_icon = " ⚠️" if (d, s_type) in boundary_exception_cells else ""
                    row[col_label] = " + ".join(staff_ids) + warning_icon
                    flags[col_label] = (d, s_type) in pre_assigned_cells
                    exception_flags[col_label] = (d, s_type) in boundary_exception_cells

            calendar_rows.append(row)
            pre_assigned_flags.append(flags)
            boundary_exception_flags.append(exception_flags)

        if calendar_rows:
            df_calendar = pd.DataFrame(calendar_rows).set_index("Datum")
            # Ensure all columns exist in correct order, fill blanks
            for col in all_cols:
                if col not in df_calendar.columns:
                    df_calendar[col] = ""
            df_calendar = df_calendar[all_cols].fillna("")

            # Build pre-assigned flag DataFrame (same shape)
            pa_flag_rows = []
            for flags in pre_assigned_flags:
                pa_flag_rows.append({col: flags.get(col, False) for col in all_cols})
            df_pa_flags = pd.DataFrame(pa_flag_rows, index=df_calendar.index)
            exception_flag_rows = []
            for flags in boundary_exception_flags:
                exception_flag_rows.append({col: flags.get(col, False) for col in all_cols})
            df_exception_flags = pd.DataFrame(exception_flag_rows, index=df_calendar.index)

            # Style: different backgrounds for night/weekend + highlight pre-assigned
            we_col_names = [label for _, label in WE_COLS]

            def highlight_cells(df: pd.DataFrame) -> pd.DataFrame:
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for row_idx in df.index:
                    for col in df.columns:
                        is_pa = df_pa_flags.at[row_idx, col] if col in df_pa_flags.columns else False
                        is_boundary_exception = (
                            df_exception_flags.at[row_idx, col]
                            if col in df_exception_flags.columns
                            else False
                        )
                        if is_boundary_exception:
                            styles.at[row_idx, col] = "background-color: #ffcc80; font-weight: bold"
                        elif is_pa:
                            # Pre-assigned: distinct teal background
                            styles.at[row_idx, col] = "background-color: #b2dfdb"
                        elif col == NIGHT_COL:
                            styles.at[row_idx, col] = "background-color: #e8e0f0"
                        elif col in we_col_names:
                            styles.at[row_idx, col] = "background-color: #fff3e0"
                return styles

            styled_calendar = df_calendar.style.apply(
                highlight_cells, axis=None
            )

            col_cfg: dict = {
                "Datum": st.column_config.TextColumn("Datum", width="small"),
                NIGHT_COL: st.column_config.TextColumn(NIGHT_COL, width="medium"),
            }
            for _, we_label in WE_COLS:
                col_cfg[we_label] = st.column_config.TextColumn(we_label, width="medium")

            st.dataframe(
                styled_calendar,
                height=700,
                use_container_width=False,
                column_config=col_cfg,
            )

            # Legend
            has_pre_assigned = any(any(f.values()) for f in pre_assigned_flags)
            legend_parts = [
                "🟣 Lila = Nachtdienst",
                "🟠 Orange = Wochenenddienst",
            ]
            if has_pre_assigned:
                legend_parts.append("🟢 Türkis = Vorgegeben (Feiertag)")
            if boundary_exceptions:
                legend_parts.append("⚠️ Orange = Ausnahme beim Block-Abstand zum Vorquartal")
            st.caption(" · ".join(legend_parts))
            if boundary_exceptions:
                with st.expander("⚠️ Ausnahmen beim Block-Abstand zum Vorquartal"):
                    st.warning(
                        "Diese Dienste nutzen die solverseitige Ausnahme für den "
                        "Block-Abstand über die Quartalsgrenze. Sie werden nicht exportiert."
                    )
                    for exception in boundary_exceptions:
                        staff_name = id_to_name.get(
                            exception.staff_identifier, exception.staff_identifier
                        )
                        st.write(
                            f"- **{staff_name}**: neuer Block am "
                            f"{exception.current_block_start.strftime('%d.%m.%Y')} nach Blockstart "
                            f"am {exception.previous_block_start.strftime('%d.%m.%Y')} "
                            f"({exception.actual_gap_days} statt mindestens "
                            f"{exception.required_gap_days} Tage)."
                        )
        else:
            st.info("Keine Einträge.")

    # --- TAB 2: STATISTICS & FAIRNESS ---
    with tab_stats:
        st.markdown("### Fairness-Analyse")
        
        if staff_list:
            # Get vacation data for available-days calculation
            vacations: list[Vacation] = st.session_state.vacations or []
            quarter_start = schedule.quarter_start
            quarter_end = schedule.quarter_end
            total_quarter_days = (quarter_end - quarter_start).days + 1
            
            # Build carry-forward delta lookup if previous context is loaded
            _prev_ctx: PreviousPlanContext | None = st.session_state.previous_context
            cf_lookup: dict[str, float] = (
                {e.identifier: e.carry_forward_delta for e in _prev_ctx.carry_forward}
                if _prev_ctx is not None
                else {}
            )
            has_cf_delta = _prev_ctx is not None

            # Compute all statistics including vacation/availability
            staff_stats = []
            for staff in staff_list:
                weekends = schedule.count_weekend_shifts(staff.identifier)
                effective_nights = schedule.count_effective_nights(staff.identifier, staff)
                total_notdienst = weekends + effective_nights

                # Vacation & availability
                avail_days = calculate_available_days(
                    staff.identifier, vacations, quarter_start, quarter_end
                )
                vacation_days = total_quarter_days - avail_days
                presence_factor = avail_days / total_quarter_days if total_quarter_days > 0 else 1.0
                
                # FTE Scaling: normalize by hours AND presence
                if staff.hours > 0 and presence_factor > 0:
                    total_notdienst_fte = (total_notdienst / staff.hours / presence_factor) * 40
                else:
                    total_notdienst_fte = 0.0
                
                cf_delta = cf_lookup.get(staff.identifier, 0.0)
                staff_stats.append({
                    "Name": staff.name,
                    "Kürzel": staff.identifier,
                    "Beruf": staff.beruf.value,
                    "Std.": staff.hours,
                    "Urlaub": vacation_days,
                    "Präsenz": round(presence_factor, 3),
                    "_weight": staff.hours * presence_factor,  # for weighted mean
                    "Nacht": "✅" if staff.nd_possible else "❌",
                    "WE": weekends,
                    "Nächte": round(effective_nights, 1),
                    "Gesamt": round(total_notdienst, 1),
                    "Norm./40h": round(total_notdienst_fte, 2),
                    "Δ Vorquartal": cf_delta,
                    "Adj. Norm.": round(total_notdienst_fte + cf_delta, 2),
                })
            
            df_stats = pd.DataFrame(staff_stats)
            
            # ========== FAIRNESS CHECK PER GROUP ==========
            def _weighted_mean(group_df: pd.DataFrame) -> float:
                """Compute hours*presence-weighted mean of Norm./40h."""
                w = group_df["_weight"]
                total_w = w.sum()
                if total_w == 0:
                    return 0.0
                return (group_df["Norm./40h"] * w).sum() / total_w

            fairness_issues: list[dict] = []
            for beruf in [Beruf.TFA, Beruf.AZUBI, Beruf.INTERN]:
                group_df = df_stats[df_stats["Beruf"] == beruf.value]
                if len(group_df) < 2:
                    continue
                
                group_mean = _weighted_mean(group_df)
                for _, row in group_df.iterrows():
                    deviation = row["Norm./40h"] - group_mean
                    if abs(deviation) >= 2.0:
                        fairness_issues.append({
                            "name": row["Name"],
                            "kuerzel": row["Kürzel"],
                            "beruf": beruf.value,
                            "value": row["Norm./40h"],
                            "group_mean": group_mean,
                            "deviation": deviation,
                            "status": "overburdened" if deviation > 0 else "underburdened",
                        })
            
            if fairness_issues:
                overburdened = [i for i in fairness_issues if i["status"] == "overburdened"]
                underburdened = [i for i in fairness_issues if i["status"] == "underburdened"]
                
                error_lines = ["**⚠️ Unfaire Verteilung innerhalb von Berufsgruppen erkannt:**\n"]
                if overburdened:
                    error_lines.append("**Überlastet** (≥2 über Gruppendurchschnitt):")
                    for item in overburdened:
                        error_lines.append(
                            f"- {item['name']} ({item['kuerzel']}, {item['beruf']}): "
                            f"{item['value']:.2f} vs. Ø {item['group_mean']:.2f} "
                            f"(+{item['deviation']:.2f})"
                        )
                if underburdened:
                    error_lines.append("\n**Unterlastet** (≥2 unter Gruppendurchschnitt):")
                    for item in underburdened:
                        error_lines.append(
                            f"- {item['name']} ({item['kuerzel']}, {item['beruf']}): "
                            f"{item['value']:.2f} vs. Ø {item['group_mean']:.2f} "
                            f"({item['deviation']:.2f})"
                        )
                st.error("\n".join(error_lines))
            else:
                st.success("✅ Faire Verteilung: Keine Mitarbeiter mit ≥2 Abweichung vom Gruppendurchschnitt.")
            
            # ========== KEY METRICS PER GROUP ==========
            st.markdown("#### 📊 Fairness-Kennzahlen pro Gruppe")
            
            group_metrics_cols = st.columns(3)
            for idx, (beruf, label, icon) in enumerate([
                (Beruf.TFA, "TFA", "👩‍⚕️"),
                (Beruf.AZUBI, "Azubi", "🎓"),
                (Beruf.INTERN, "Intern", "🩺"),
            ]):
                group_df = df_stats[df_stats["Beruf"] == beruf.value]
                with group_metrics_cols[idx]:
                    st.markdown(f"### {icon} {label}")
                    st.caption(f"{len(group_df)} Mitarbeiter")
                    if len(group_df) >= 2:
                        g_vals = group_df["Norm./40h"]
                        g_wmean = _weighted_mean(group_df)
                        spread = g_vals.max() - g_vals.min()
                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("Ø Norm./40h", f"{g_wmean:.2f}",
                                      help="Gewichteter Durchschnitt (Std. × Anwesenheit)")
                            st.metric("Min", f"{g_vals.min():.2f}")
                        with c2:
                            st.metric("Spread", f"{spread:.2f}", help="Max - Min (niedriger = fairer)")
                            st.metric("Max", f"{g_vals.max():.2f}")
                    elif len(group_df) == 1:
                        st.metric("Norm./40h", f"{group_df['Norm./40h'].iloc[0]:.2f}")
                        st.caption("Nur 1 MA — kein Vergleich möglich")
                    else:
                        st.caption("Keine Mitarbeiter in dieser Gruppe")

            # ========== DETAILED TABLES BY GROUP ==========
            st.markdown("---")
            st.markdown("#### 📋 Detailansicht nach Berufsgruppe")
            st.caption(
                "Farbkodierung (Norm./40h): 🟢 innerhalb ±1.0 vom Ø (fair), "
                "🟡 ±1.0–2.0 (leichte Abweichung), 🔴 >±2.0 (signifikant)  —  "
                "Normalisierung: Notdienst ÷ Vertragsstd. ÷ Anwesenheitsfaktor × 40"
            )
            if has_cf_delta:
                st.caption(
                    "**Δ Vorquartal**: Carry-Forward aus dem Vorquartal — "
                    "**positiv (+)**: letztes Quartal mehr als Ø geleistet → Entlastung im aktuellen Quartal erwartet. "
                    "**negativ (−)**: weniger als Ø geleistet → stärkere Einplanung jetzt erwartet. "
                    "**Adj. Norm.** = Norm./40h + Δ = bereinigter Fairness-Wert (maßgeblich für die Beurteilung)."
                )

            # Columns to display in detail tables (condensed)
            detail_cols = ["Name", "Kürzel", "Std.", "Urlaub", "Nacht", "WE", "Nächte", "Gesamt", "Norm./40h"]
            if has_cf_delta:
                detail_cols = detail_cols + ["Δ Vorquartal", "Adj. Norm."]
            
            def style_group_table(
                df: pd.DataFrame, group_mean: float, adj_mean: float | None = None
            ) -> pd.io.formats.style.Styler:
                """Color the Norm./40h, Δ Vorquartal, and Adj. Norm. columns."""

                def color_norm(val: float) -> str:
                    """Soft shading — current-quarter position relative to group mean."""
                    abs_dev = abs(val - group_mean)
                    if abs_dev <= 1.0:
                        return "background-color: #e8f5e9"  # soft green
                    elif abs_dev <= 2.0:
                        return "background-color: #fff8e1"  # soft yellow
                    return "background-color: #ffebee"  # soft red

                def color_delta(val: float) -> str:
                    """Diverging warm/cool — direction of carry-forward."""
                    if val > 0.5:
                        return "background-color: #ffe0b2"  # warm orange: overworked last Q
                    if val < -0.5:
                        return "background-color: #e3f2fd"  # cool blue: underworked last Q
                    return ""  # near-zero: no fill

                def color_adj(val: float) -> str:
                    """Primary fairness metric — bold green / yellow / red."""
                    ref = adj_mean if adj_mean is not None else group_mean
                    abs_dev = abs(val - ref)
                    if abs_dev <= 1.0:
                        return "background-color: #66bb6a; font-weight: bold"
                    elif abs_dev <= 2.0:
                        return "background-color: #ffee58; font-weight: bold"
                    return "background-color: #ef5350; color: white; font-weight: bold"

                fmt: dict = {
                    "Nächte": "{:.1f}",
                    "Gesamt": "{:.1f}",
                    "Norm./40h": "{:.2f}",
                }
                styled = df.style.applymap(color_norm, subset=["Norm./40h"])
                if has_cf_delta and "Δ Vorquartal" in df.columns:
                    styled = styled.applymap(color_delta, subset=["Δ Vorquartal"])
                    fmt["Δ Vorquartal"] = lambda v: f"+{v:.2f}" if v > 0 else f"{v:.2f}"
                if has_cf_delta and "Adj. Norm." in df.columns:
                    styled = styled.applymap(color_adj, subset=["Adj. Norm."])
                    fmt["Adj. Norm."] = "{:.2f}"
                return styled.format(fmt)
            
            # TFA Table
            df_tfa_full = df_stats[df_stats["Beruf"] == "TFA"]
            df_tfa = df_tfa_full[detail_cols].copy()
            if not df_tfa.empty:
                tfa_mean = _weighted_mean(df_tfa_full)
                tfa_adj_mean: float | None = (
                    float(
                        (df_tfa_full["Adj. Norm."] * df_tfa_full["_weight"]).sum()
                        / df_tfa_full["_weight"].sum()
                    )
                    if has_cf_delta else None
                )
                st.markdown(f"##### 👩‍⚕️ TFA ({len(df_tfa)} MA, Ø {tfa_mean:.2f} Norm./40h)")
                st.dataframe(
                    style_group_table(df_tfa, tfa_mean, tfa_adj_mean),
                    use_container_width=True,
                    height=min(400, 35 * len(df_tfa) + 38),
                )
            
            # Azubi Table
            df_azubi_full = df_stats[df_stats["Beruf"] == "Azubi"]
            df_azubi = df_azubi_full[detail_cols].copy()
            if not df_azubi.empty:
                azubi_mean = _weighted_mean(df_azubi_full)
                azubi_adj_mean: float | None = (
                    float(
                        (df_azubi_full["Adj. Norm."] * df_azubi_full["_weight"]).sum()
                        / df_azubi_full["_weight"].sum()
                    )
                    if has_cf_delta else None
                )
                st.markdown(f"##### 🎓 Azubi ({len(df_azubi)} MA, Ø {azubi_mean:.2f} Norm./40h)")
                st.dataframe(
                    style_group_table(df_azubi, azubi_mean, azubi_adj_mean),
                    use_container_width=True,
                    height=min(400, 35 * len(df_azubi) + 38),
                )
            
            # Intern Table
            df_intern_full = df_stats[df_stats["Beruf"] == "Intern"]
            df_intern = df_intern_full[detail_cols].copy()
            if not df_intern.empty:
                intern_mean = _weighted_mean(df_intern_full)
                intern_adj_mean: float | None = (
                    float(
                        (df_intern_full["Adj. Norm."] * df_intern_full["_weight"]).sum()
                        / df_intern_full["_weight"].sum()
                    )
                    if has_cf_delta else None
                )
                st.markdown(f"##### 🩺 Intern ({len(df_intern)} MA, Ø {intern_mean:.2f} Norm./40h)")
                st.dataframe(
                    style_group_table(df_intern, intern_mean, intern_adj_mean),
                    use_container_width=True,
                    height=min(400, 35 * len(df_intern) + 38),
                )

            # ========== ACTIONABLE INSIGHTS ==========
            st.markdown("---")
            st.markdown("#### 🎯 Handlungsempfehlungen")
            
            recommendations = []
            for beruf in [Beruf.TFA, Beruf.AZUBI, Beruf.INTERN]:
                group_df = df_stats[df_stats["Beruf"] == beruf.value]
                if len(group_df) < 2:
                    continue
                
                group_mean = _weighted_mean(group_df)
                group_spread = group_df["Norm./40h"].max() - group_df["Norm./40h"].min()
                
                if group_spread > 3.0:
                    high_load = group_df[group_df["Norm./40h"] > group_mean + 1.5]
                    low_load = group_df[group_df["Norm./40h"] < group_mean - 1.5]
                    
                    high_names = ", ".join(high_load["Name"].tolist()) if not high_load.empty else "-"
                    low_names = ", ".join(low_load["Name"].tolist()) if not low_load.empty else "-"
                    
                    recommendations.append({
                        "group": beruf.value,
                        "spread": group_spread,
                        "high_load": high_names,
                        "low_load": low_names,
                    })
            
            if recommendations:
                st.warning("**Ungleichgewicht innerhalb von Gruppen:**")
                for rec in recommendations:
                    st.markdown(
                        f"**{rec['group']}** (Spread: {rec['spread']:.2f}): "
                        f"Überlastet: {rec['high_load']} · Unterlastet: {rec['low_load']}"
                    )
            else:
                st.success("✅ Alle Gruppen haben eine ausgewogene interne Verteilung (Spread ≤ 3.0).")

            # ========== SCORE BREAKDOWN EXPANDER ==========
            with st.expander("📈 Optimierungs-Score: Aufschlüsselung"):
                if validation_result is None:
                    st.info("Kein Validierungsergebnis verfügbar.")
                else:
                    total_score = validation_result.soft_penalty
                    total_hours_all = sum(s.hours for s in staff_list)
                    total_assignments = len(schedule.assignments)

                    # -- Component 1: proportional deviation --
                    prop_rows = []
                    total_prop_penalty = 0.0
                    for _s in staff_list:
                        actual = schedule.count_total_notdienst(_s.identifier, _s)
                        target = (
                            (_s.hours / total_hours_all) * total_assignments
                            if total_hours_all > 0
                            else 0.0
                        )
                        deviation = actual - target
                        contribution = deviation**2
                        total_prop_penalty += contribution
                        prop_rows.append(
                            {
                                "Name": _s.name,
                                "Beruf": _s.beruf.value,
                                "Std.": _s.hours,
                                "Ist": round(actual, 1),
                                "Soll (∝ Std.)": round(target, 1),
                                "Differenz": round(deviation, 1),
                                "Beitrag (Δ²)": round(contribution, 2),
                            }
                        )

                    # -- Component 2: within-group fairness (std dev × 10) --
                    group_rows = []
                    total_group_penalty = 0.0
                    for _beruf in [Beruf.TFA, Beruf.AZUBI, Beruf.INTERN]:
                        _grp = [s for s in staff_list if s.beruf == _beruf]
                        if len(_grp) < 2:
                            continue
                        _counts = [
                            schedule.count_total_notdienst(s.identifier, s) for s in _grp
                        ]
                        _mean = sum(_counts) / len(_counts)
                        _variance = sum((x - _mean) ** 2 for x in _counts) / len(_counts)
                        _std = _variance**0.5
                        _contrib = _std * 10
                        total_group_penalty += _contrib
                        group_rows.append(
                            {
                                "Gruppe": _beruf.value,
                                "MA": len(_grp),
                                "Ø Notdienste": round(_mean, 2),
                                "Std.-Abw.": round(_std, 2),
                                "× Faktor": 10,
                                "Penalty-Beitrag": round(_contrib, 2),
                            }
                        )

                    # -- Component 3: soft violations (nd_max_consecutive) --
                    violation_penalty = max(
                        0.0,
                        round(total_score - total_prop_penalty - total_group_penalty, 4),
                    )
                    n_violations = round(violation_penalty / 100)

                    # --- Header ---
                    st.markdown(
                        f"**Gesamt-Score: {total_score:.2f} Punkte** "
                        "*(niedriger = fairer und regelkonformer Plan; 0 = optimal)*"
                    )
                    st.caption(
                        "Der Score setzt sich aus drei unabhängigen Komponenten zusammen. "
                        "Jede misst eine andere Dimension der Planqualität."
                    )
                    st.markdown("---")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(
                            "① Proportionale Abweichung",
                            f"{total_prop_penalty:.2f}",
                            help=(
                                "Summe (Ist − Soll)² über alle Mitarbeiter. "
                                "Soll = Stunden-Anteil × Gesamtdienste."
                            ),
                        )
                    with col2:
                        st.metric(
                            "② Gruppen-Fairness",
                            f"{total_group_penalty:.2f}",
                            help="Std.-Abw. der Notdienste pro Berufsgruppe × 10.",
                        )
                    with col3:
                        st.metric(
                            "③ Soft-Regelverstöße",
                            f"{violation_penalty:.2f}",
                            help=(
                                "100 Punkte pro Verstoß gegen nd_max_consecutive "
                                "(aufeinanderfolgende Nächte überschreiten das Maximum)."
                            ),
                        )

                    st.markdown("---")

                    # --- Detail: Component 1 ---
                    st.markdown("##### ① Proportionale Abweichung — pro Mitarbeiter")
                    st.caption(
                        f"**{total_prop_penalty:.2f} Punkte** · "
                        f"Formel: Σ (Ist − Soll)²  ·  "
                        f"Soll = Std./Gesamtstd. × {total_assignments} Dienste"
                    )

                    def _color_contrib(val: float) -> str:
                        if val < 0.5:
                            return "background-color: #e8f5e9"
                        if val < 2.0:
                            return "background-color: #fff8e1"
                        return "background-color: #ffebee"

                    df_prop = pd.DataFrame(prop_rows).sort_values(
                        "Beitrag (Δ²)", ascending=False
                    )
                    st.dataframe(
                        df_prop.style.applymap(_color_contrib, subset=["Beitrag (Δ²)"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    # --- Detail: Component 2 ---
                    if group_rows:
                        st.markdown("##### ② Gruppen-Fairness — pro Berufsgruppe")
                        st.caption(
                            f"**{total_group_penalty:.2f} Punkte** · "
                            "Formel: Std.-Abw.(Notdienste) × 10 pro Gruppe"
                        )
                        st.dataframe(
                            pd.DataFrame(group_rows),
                            use_container_width=True,
                            hide_index=True,
                        )

                    # --- Detail: Component 3 ---
                    st.markdown("##### ③ Soft-Regelverstöße (nd_max_consecutive)")
                    if violation_penalty > 0.1:
                        st.warning(
                            f"⚠️ ~{n_violations} Verstoß/Verstöße gegen `nd_max_consecutive` "
                            f"erkannt → {violation_penalty:.0f} Punkte. "
                            "Details auf dem Tab '✅ Validierung'."
                        )
                    else:
                        st.success("✅ Keine Soft-Regelverstöße (0 Punkte)")

            # Breakdown explanation
            with st.expander("ℹ️ Berechnungslogik"):
                st.markdown(r"""
                **Notdienst Gesamt** = Wochenend-Schichten + Effektive Nächte
                
                - **Wochenend-Schichten**: Jede WE-Schicht zählt 1×
                - **Effektive Nächte**: 
                  - TFA/Intern: Paar-Nacht = 0.5×, Solo-Nacht = 1.0×
                  - Azubi: Immer 1.0× (auch bei Paarung)
                
                **Normalisierung** (Norm./40h):
                
                $$\frac{\text{Notdienst Gesamt}}{\text{Vertragsstd.} \times \text{Anwesenheitsfaktor}} \times 40$$
                
                Anwesenheitsfaktor = $\frac{\text{Verfügbare Tage}}{\text{Quartalstage}}$
                
                → Ein Mitarbeiter mit 20h-Vertrag und 10% Urlaub wird auf das gleiche
                Niveau normalisiert wie jemand mit 40h und 0% Urlaub.
                
                **Spalten in der Detailansicht:**
                - **Urlaub**: Urlaubstage im Quartal
                - **Nacht**: Ob Nachtdienst möglich ist (✅/❌)
                - **WE / Nächte**: Absolute Anzahl zugewiesener Schichten
                - **Gesamt**: WE + Eff. Nächte
                - **Norm./40h**: Normalisierter Quartalswert (Vergleichsbasis)
                - **Δ Vorquartal**: Carry-Forward — positiv = mehr geleistet, negativ = weniger geleistet
                - **Adj. Norm.**: Norm./40h + Δ = bereinigter Fairness-Wert *(primärer Indikator)*
                
                **Fairness-Schwellwert**: ≥2.0 Abweichung vom Gruppendurchschnitt = unfair.
                
                **Farbkodierung** (relativ zur Berufsgruppe):
                - **Norm./40h** (soft): 🟢 ±1.0 fair · 🟡 ±1.0–2.0 leicht · 🔴 >±2.0 signifikant
                - **Δ Vorquartal**: 🟠 Warm = mehr geleistet letztes Q · 🔵 Kühl = weniger geleistet
                - **Adj. Norm.** (fett, primär): 🟢 ±1.0 · 🟡 ±1.0–2.0 · 🔴 >±2.0 — relativ zum bereinigten Gruppenø
                """)

    # --- TAB 3: VALIDATION ---
    with tab_validation:
        st.markdown("### Validierung & constraints")
        
        if validation_result:
            if validation_result.is_valid():
                st.success(f"✅ Plan ist valide! (Soft Penalty Score: {validation_result.soft_penalty:.2f})")
            else:
                st.error(f"❌ {len(validation_result.hard_violations)} harte Regelverstöße gefunden.")

            st.markdown("#### Harte Constraints (Muss-Regeln)")
            
            # Map Constraint Name -> Description
            known_constraints = {
                "Minor Sunday Ban": "Keine Minderjährigen am Sonntag",
                "Intern Weekend Ban": "Keine Interns am Wochenende",
                "Azubi Night Pairing": "Azubi Nachtdienst nur mit TFA/Intern",
                "Multiple Azubis on Night": "Max. 1 Azubi pro Nachtschicht",
                "Intern Night No Non-Azubi": "Mind. 1 TFA/Intern pro Nacht (So-Mo, Mo-Di)",
                "Night Pairing Required": "Mitarbeiter ohne 'nd_alone' nur im Team",
                "ND Alone Improper Pairing": "nd_alone=True muss alleine arbeiten",
                "Min Consecutive Nights": "Min. aufeinanderfolgende Nächte (nd_min_consecutive)",
                "Night/Day Conflict": "Ruhezeiten: Kein Tagdienst an/nach Nachtdienst",
                "2-Week Block Limit": "Max. 1 Block pro 2 Wochen",
                "Weekend Isolation": "Wochenend-Schichten nicht in Blöcken",
                "ND Exception Weekday": "Beachtung blockierter Wochentage (nd_exceptions)",
                "Shift Eligibility": "Qualifikation für Schicht",
                "Shift Coverage": "Mindestbesetzung (Nachts)",
                "Abteilung Same Night": "Gleiche Abteilung (OP/Station) nicht zusammen nachts",
                "Abteilung Consecutive Days": "Gleiche Abteilung (OP/Station) nicht aufeinander folgend",
            }

            # Map violations
            violations_map = {}
            for v in validation_result.hard_violations:
                if v.constraint_name not in violations_map:
                    violations_map[v.constraint_name] = []
                violations_map[v.constraint_name].append(v.description)

            # Check known constraints
            col_a, col_b = st.columns(2)
            
            items = list(known_constraints.items())
            mid = (len(items) + 1) // 2
            
            for i, (name, display_name) in enumerate(items):
                target_col = col_a if i < mid else col_b
                
                with target_col:
                    if name in violations_map:
                        st.error(f"❌ {display_name}")
                        with st.expander(f"Details ({len(violations_map[name])})"):
                            for msg in violations_map[name]:
                                st.write(f"- {msg}")
                    else:
                        st.success(f"✅ {display_name}")

            # Unknown violations
            active_known = set(known_constraints.keys())
            unknown_violations = [v for v in validation_result.hard_violations if v.constraint_name not in active_known]
            if unknown_violations:
                st.warning(f"⚠️ Sonstige Fehler ({len(unknown_violations)})")
                for v in unknown_violations:
                    st.write(f"- [{v.constraint_name}] {v.description}")

            st.markdown("---")
            st.info(f"ℹ️ **Soft Penalty Score**: {validation_result.soft_penalty:.1f} (Niedriger ist fairer)")

        else:
            st.info("Bitte Plan validieren.")


def page_export() -> None:
    """Page: Export schedule."""
    st.title("💾 Export")

    if st.session_state.schedule is None:
        st.warning("⚠️ Bitte zuerst einen Plan erstellen")
        return

    schedule = st.session_state.schedule
    staff_list: list[Staff] | None = st.session_state.staff_list

    st.markdown("### Dienstplan exportieren")

    # Prepare export data
    assignment_data = []
    for assignment in sorted(schedule.assignments, key=lambda a: a.shift.shift_date):
        assignment_data.append(
            {
                "Wochentag": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][
                    assignment.shift.shift_date.weekday()
                ],
                "Datum": assignment.shift.shift_date.strftime("%d.%m.%Y"),
                "Mitarbeiter": assignment.staff_identifier,
                "Schicht": assignment.shift.shift_type.value,
                "Paarweise": "Ja" if assignment.is_paired else "Nein",
            }
        )

    df_export = pd.DataFrame(assignment_data)

    # Split into the two export sheets
    df_nights = df_export[df_export["Schicht"].str.startswith("N_")].reset_index(drop=True)
    df_weekends = df_export[~df_export["Schicht"].str.startswith("N_")].reset_index(drop=True)

    # Excel download — two sheets: nights and weekends
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        df_nights.to_excel(writer, sheet_name="Nachtdienste", index=False)
        df_weekends.to_excel(writer, sheet_name="Wochenenddienste", index=False)
    excel_data = excel_buffer.getvalue()

    st.download_button(
        label="📥 Als Excel herunterladen",
        data=excel_data,
        file_name=f"dienstplan_{schedule.quarter_start.strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="content",
    )

    # Preview — tabbed by sheet
    st.markdown("---")
    st.markdown("### Vorschau")
    tab_prev_nights, tab_prev_weekends = st.tabs(["🌙 Nachtdienste", "☀️ Wochenenddienste"])
    with tab_prev_nights:
        st.caption(f"{len(df_nights)} Einträge")
        st.dataframe(df_nights, use_container_width=True, height=500)
    with tab_prev_weekends:
        st.caption(f"{len(df_weekends)} Einträge")
        st.dataframe(df_weekends, use_container_width=True, height=500)


if __name__ == "__main__":
    main()
