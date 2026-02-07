"""Streamlit app for Notdienst scheduling."""

import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import hashlib
import os
from scheduler.models import (
    Beruf,
    ShiftType,
    Staff,
    Vacation,
    load_staff_from_csv,
    load_vacations_from_csv,
)
from scheduler.solver import SolverBackend, generate_schedule
from scheduler.validator import validate_schedule

# Page config
st.set_page_config(page_title="Dienstplan Generator", page_icon="📅", layout="wide")


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
    page = st.sidebar.radio(
        "Navigation",
        [
            "Laden / CSV",
            "Personal",
            "Urlaub",
            "Regeln",
            "Plan erstellen",
            "Plan anzeigen",
            "Export",
        ],
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

    # Route to pages
    if page == "Laden / CSV":
        page_load_csv()
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


def page_load_csv() -> None:
    """Page: Load staff data from CSV."""
    st.title("📂 Daten laden")

    st.markdown("### Personaldaten hochladen")
    uploaded_file = st.file_uploader(
        "CSV-Datei mit Personalinformationen",
        type=["csv"],
        help="Erwartet: name, identifier, adult, hours, beruf, reception, nd_possible, nd_alone, nd_count, nd_exceptions",
    )

    if uploaded_file is not None:
        try:
            # Save to temp file and load
            temp_path = Path("temp_staff.csv")
            with temp_path.open("wb") as f:
                f.write(uploaded_file.getvalue())

            staff_list = load_staff_from_csv(temp_path)
            st.session_state.staff_list = staff_list

            st.success(f"✅ {len(staff_list)} Mitarbeiter erfolgreich geladen!")

            # Show preview
            st.markdown("### Vorschau")
            df = pd.DataFrame([s.model_dump() for s in staff_list])
            st.dataframe(df, width="content")

            # Cleanup
            temp_path.unlink(missing_ok=True)

        except Exception as e:
            st.error(f"❌ Fehler beim Laden der CSV: {e}")

    # Vacation data upload
    st.markdown("---")
    st.markdown("### Urlaub / Verfügbarkeit hochladen")
    vacation_file = st.file_uploader(
        "CSV-Datei mit Urlaubsdaten (optional)",
        type=["csv"],
        key="vacation_upload",
        help="Erwartet: identifier, start_date, end_date (Datumsformat: YYYY-MM-DD)",
    )
    
    if vacation_file is not None:
        try:
            temp_path = Path("temp_vacations.csv")
            with temp_path.open("wb") as f:
                f.write(vacation_file.getvalue())
            
            vacations = load_vacations_from_csv(temp_path)
            st.session_state.vacations = vacations
            
            st.success(f"✅ {len(vacations)} Urlaubseinträge erfolgreich geladen!")
            
            # Show preview
            st.markdown("### Vorschau")
            df = pd.DataFrame([v.model_dump() for v in vacations])
            st.dataframe(df, width="content")
            
            temp_path.unlink(missing_ok=True)
            
        except Exception as e:
            st.error(f"❌ Fehler beim Laden der Urlaubsdaten: {e}")

    # Show current status
    st.markdown("---")
    st.markdown("### 📊 Aktueller Status")
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.staff_list:
            st.success(f"✅ {len(st.session_state.staff_list)} Mitarbeiter geladen")
        else:
            st.warning("⚠️ Noch keine Personaldaten geladen")
    with col2:
        if st.session_state.vacations:
            st.success(f"✅ {len(st.session_state.vacations)} Urlaubseinträge geladen")
        else:
            st.info("ℹ️ Keine Urlaubsdaten geladen (optional)")


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


def page_personal() -> None:
    """Page: View and filter staff data."""
    st.title("👥 Personal")

    if st.session_state.staff_list is None:
        st.warning("⚠️ Bitte zuerst Personaldaten laden (Seite 'Laden / CSV')")
        return

    staff_list: list[Staff] = st.session_state.staff_list

    # Search box for name/identifier
    st.markdown("### 🔍 Mitarbeiter suchen")
    search_query = st.text_input(
        "Name oder Kürzel eingeben",
        placeholder="z.B. 'Müller' oder 'MM'",
        help="Suche nach Name oder Identifier (Groß-/Kleinschreibung wird ignoriert)",
    )

    # Filters
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

    # Apply filters
    filtered = staff_list
    
    # Text search filter (name or identifier)
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

    # Display table
    st.markdown(f"### Mitarbeiter ({len(filtered)} von {len(staff_list)})")
    df = pd.DataFrame([s.model_dump() for s in filtered])
    st.dataframe(df, width="content", height=600)

    # Statistics
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


def page_regeln() -> None:
    """Page: Display constraint rules."""
    st.title("📋 Regeln & Constraints")

    st.markdown("""
    ## Hard Constraints (müssen erfüllt sein)

    ### Wochenend-Schichten
    - **Samstag 10-19**: Alle Azubis (Azubidienst)
    - **Samstag 10-21**: Azubis mit `reception=True` oder TFA (Anmeldung)
    - **Samstag 10-22 / Sonntag 8-20 / Sonntag 10-22**: Nur TFA
    - **Sonntag 8-20:30**: Nur erwachsene Azubis (≥18 Jahre)
    - **Minderjährige**: Dürfen **nicht** sonntags arbeiten
    - **Interns**: Arbeiten **nie** am Wochenende
    - **Max. 1 Schicht/Tag**: Jede Person kann max. 1 Schicht pro Tag haben
    - **Wochenend-Isolation**: WE-Schichten können nicht Teil eines Blocks sein

    ### Nachtdienste
    - **Alle Nächte**: 1-2 Personen, mind. 1 nicht-Azubi (TFA oder Intern)
    - **Sonntag→Montag / Montag→Dienstag**: Genau 1 TFA/Intern + optional 1 Azubi
    - **Azubis**: Müssen **immer** mit einem TFA oder Intern zusammenarbeiten
    - **Azubi effektive Nächte**: Zählen immer 1.0× (auch bei Paarung)
    - **Zwei Azubis**: Können **nie** zusammen Nachtdienst machen
    - **nd_alone=False**: Mitarbeiter müssen paarweise arbeiten (außer So→Mo, Mo→Di)
    - **nd_alone=True**: Mitarbeiter arbeiten **komplett alleine** (keine Paarung erlaubt)
    - **Min. 2 Nächte**: TFA und Interns müssen mind. 2 aufeinanderfolgende Nächte arbeiten
    - **Interns**: Arbeiten 2-3 Nächte/Monat (6-9 pro Quartal)

    ### Abteilungs-Constraint
    - **Abteilung (OP/Station)**: Mitarbeiter derselben Abteilung (`op` oder `station`) dürfen:
      - **Nicht zusammen** auf derselben Nachtschicht arbeiten
      - **Nicht aufeinanderfolgend** Nachtschichten machen (Tag N und Tag N+1)
    - **Begründung**: Verhindert Kapazitätsengpässe in Spezialgebieten
    - **Ausnahme**: Mitarbeiter mit `abteilung=other` sind von dieser Regel ausgenommen

    ### Zeitliche Constraints
    - **2-Wochen-Regel**: Max. 1 zusammenhängender Schichtblock pro 2-Wochen-Fenster
    - **Nacht/Tag-Konflikt**: Kein Tagdienst am selben oder nächsten Tag nach Nachtschicht
    - **nd_exceptions**: Keine Nächte an Wochentagen in `nd_exceptions` (1=Mo, 7=So)

    ## Soft Constraints (Optimierungsziele)

    - **nd_max_consecutive**: Max. aufeinanderfolgende Nächte (wird möglichst eingehalten)
    - **Faire Verteilung**: Notdienste (WE + Nächte kombiniert) proportional zu Wochenstunden
    - **Effective Nights**: TFA/Intern: Paar-Nächte = 0,5×, Solo-Nächte = 1,0×; Azubi: immer 1,0×
    - **Gruppen-Fairness**: Minimale Abweichung (±2) innerhalb TFA/Azubi/Intern

    ### Penalty-System
    - Abweichung von Ziel → Quadratische Strafe
    - Ungleichheit in Gruppe → Standardabweichung × 10
    - nd_max_consecutive Überschreitung → 100 pro Verletzung
    """)

    st.markdown("---")
    st.info(
        "💡 **Tipp**: Bei nicht erfüllbaren Constraints wird eine Liste der Verletzungen "
        "angezeigt. Verwende den Button 'Entspannungen vorschlagen', um Lösungen zu finden."
    )


def page_plan_erstellen() -> None:
    """Page: Generate schedule."""
    st.title("🔨 Plan erstellen")

    if st.session_state.staff_list is None:
        st.warning("⚠️ Bitte zuerst Personaldaten laden (Seite 'Laden / CSV')")
        return

    st.markdown("### Quartal auswählen")
    col1, col2 = st.columns(2)
    with col1:
        quarter = st.selectbox("Quartal", ["Q1", "Q2", "Q3", "Q4"], index=1)
    with col2:
        year = st.number_input("Jahr", min_value=2024, max_value=2030, value=2026)

    # Calculate quarter start
    quarter_starts = {
        "Q1": date(year, 1, 1),
        "Q2": date(year, 4, 1),
        "Q3": date(year, 7, 1),
        "Q4": date(year, 10, 1),
    }
    quarter_start = quarter_starts[quarter]

    st.info(f"📅 Zeitraum: {quarter_start.strftime('%d.%m.%Y')} - ca. 91 Tage")
    
    # Show vacation status
    vacations = st.session_state.vacations or []
    if vacations:
        st.success(f"✅ {len(vacations)} Urlaubseinträge werden berücksichtigt")
    else:
        st.info("ℹ️ Keine Urlaubsdaten geladen - alle Mitarbeiter gelten als verfügbar")

    # Solver parameters
    st.markdown("---")
    st.markdown("### Solver-Einstellungen")
    
    # Solver backend selection
    solver_backend = st.selectbox(
        "Solver-Backend",
        options=[SolverBackend.CPSAT, SolverBackend.HEURISTIC],
        format_func=lambda x: "CP-SAT (OR-Tools) - empfohlen" if x == SolverBackend.CPSAT else "Heuristik (Greedy + Local Search)",
        index=0,
        help="CP-SAT garantiert optimale Fairness, Heuristik ist schneller aber weniger fair",
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if solver_backend == SolverBackend.CPSAT:
            max_time = st.number_input(
                "Max. Lösungszeit (Sekunden)", min_value=30, max_value=600, value=120, step=30
            )
            max_iterations = max_time * 20  # Convert to iterations scale
        else:
            max_iterations = st.number_input(
                "Max. Iterationen", min_value=100, max_value=10000, value=2000, step=100
            )
    with col2:
        random_seed = st.number_input(
            "Random Seed (optional)", min_value=0, max_value=9999, value=42, step=1
        )

    # Show eligibility information
    st.markdown("---")
    with st.expander("ℹ️ Mindestschicht-Anforderungen (Eligibility-Logik)", expanded=False):
        st.markdown("""
        **Neue Regel:** Jeder berechtigte Mitarbeiter muss mindestens **1 Wochenend-Schicht** 
        und **1 Nacht-Schicht** pro Quartal übernehmen.
        
        **Ausnahmen:**
        - **Interns**: Arbeiten nie am Wochenende (nur Nachtdienste)
        - **Mitarbeiter ohne `nd_possible`**: Keine Nachtdienst-Pflicht
        - **Eingeschränkte Verfügbarkeit**: Mitarbeiter mit weniger als `nd_min_consecutive` 
          verfügbaren Nachttypen sind von der Nacht-Pflicht befreit
        
        **Fairness-Berechnung:** Die Anzahl der erwarteten Notdienste wird jetzt sowohl nach 
        **Arbeitsstunden** als auch nach **Anwesenheitstagen** (abzgl. Urlaub) normalisiert.
        """)

    # Generate button
    st.markdown("---")
    if st.button("🚀 Plan generieren", type="primary"):
        spinner_msg = "⏳ Generiere Dienstplan mit CP-SAT..." if solver_backend == SolverBackend.CPSAT else "⏳ Generiere Dienstplan..."
        with st.spinner(spinner_msg):
            try:
                staff_list: list[Staff] = st.session_state.staff_list
                result = generate_schedule(
                    staff_list,
                    quarter_start,
                    vacations=vacations,
                    max_iterations=max_iterations,
                    random_seed=random_seed,
                    backend=solver_backend,
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
                    st.metric("Soft Penalty", f"{validation.soft_penalty:.2f}")

                    # Show alternatives
                    if len(result.schedules) > 1:
                        st.markdown("### Alternative Lösungen")
                        for i, (_sched, penalty) in enumerate(
                            zip(result.schedules[1:], result.penalties[1:], strict=True), start=2
                        ):
                            st.text(f"Lösung {i}: Penalty = {penalty:.2f}")

                else:
                    st.error("❌ Keine gültige Lösung gefunden!")
                    st.markdown("### Verletzungen der Hard Constraints:")
                    for constraint in result.unsatisfiable_constraints:
                        st.text(f"• {constraint}")

                    if st.button("💡 Entspannungen vorschlagen"):
                        st.info(
                            "Vorschläge:\n"
                            "- Reduziere 3-Wochen-Regel auf 2 Wochen\n"
                            "- Erlaube Azubis mehr Solo-Nächte (So-Mo, Mo-Di mit TA)\n"
                            "- Erhöhe nd_count Flexibilität für einige Mitarbeiter"
                        )

            except Exception as e:
                st.error(f"❌ Fehler beim Generieren: {e}")
                st.exception(e)

    # Current status
    st.markdown("---")
    if st.session_state.schedule:
        st.success("✅ Plan vorhanden - wechsle zu 'Plan anzeigen'")
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
        
        # New descriptive labels for weekend shifts
        SHIFT_DISPLAY_LABELS = {
            ShiftType.SATURDAY_10_21: "Sa 10-21: Anmeldung/Ruf",
            ShiftType.SATURDAY_10_22: "Sa 10-22: Rufbereitschaft",
            ShiftType.SATURDAY_10_19: "Sa 10-19: Azubidienst",
            ShiftType.SUNDAY_8_20: "So 08-20: Dienst",
            ShiftType.SUNDAY_10_22: "So 10-22: Rufbereitschaft",
            ShiftType.SUNDAY_8_2030: "So 08-20:30: Azubi/Ruf",
        }

        # Logical week order for columns: Nights first, then Weekends
        WEEK_ORDER = [
            # Night shifts
            ShiftType.NIGHT_MON_TUE,
            ShiftType.NIGHT_TUE_WED,
            ShiftType.NIGHT_WED_THU,
            ShiftType.NIGHT_THU_FRI,
            ShiftType.NIGHT_FRI_SAT,
            ShiftType.NIGHT_SAT_SUN,
            ShiftType.NIGHT_SUN_MON,
            # Weekend shifts
            ShiftType.SATURDAY_10_19,
            ShiftType.SATURDAY_10_21,
            ShiftType.SATURDAY_10_22,
            ShiftType.SUNDAY_8_20,
            ShiftType.SUNDAY_10_22,
            ShiftType.SUNDAY_8_2030,
        ]

        # Matrix: Date x ShiftType -> Staff
        # 1. Map (Date, Shift) -> [Staff1, Staff2]
        shift_map = {}
        unique_dates = sorted(list(set(a.shift.shift_date for a in schedule.assignments)))
        
        for assignment in schedule.assignments:
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            if key not in shift_map:
                shift_map[key] = []
            # Use name or identifier based on toggle
            display_value = (
                id_to_name.get(assignment.staff_identifier, assignment.staff_identifier)
                if show_names
                else assignment.staff_identifier
            )
            shift_map[key].append(display_value)

        # 2. Build rows
        calendar_rows = []
        for d in unique_dates:
            row = {"Datum": d.strftime("%d.%m.%Y (%a)")}
            for s_type in WEEK_ORDER:
                staff_ids = shift_map.get((d, s_type), [])
                if staff_ids:
                    col_name = SHIFT_DISPLAY_LABELS.get(s_type, s_type.value)
                    row[col_name] = " + ".join(staff_ids)
            calendar_rows.append(row)

        if calendar_rows:
            df_calendar = pd.DataFrame(calendar_rows)
            df_calendar.set_index("Datum", inplace=True)
            
            # Reindex to ensure strictly logical column order (only present columns)
            ordered_cols = [
                SHIFT_DISPLAY_LABELS.get(s, s.value) 
                for s in WEEK_ORDER 
                if SHIFT_DISPLAY_LABELS.get(s, s.value) in df_calendar.columns
            ]
            df_calendar = df_calendar.reindex(columns=ordered_cols)
            
            st.dataframe(
                df_calendar, 
                height=700, 
                width="stretch",
                column_config={
                    "Datum": st.column_config.TextColumn("Datum")
                }
            )
        else:
            st.info("Keine Einträge.")

    # --- TAB 2: STATISTICS & FAIRNESS ---
    with tab_stats:
        st.markdown("### Fairness-Analyse")
        
        if staff_list:
            # Compute all statistics
            staff_stats = []
            for staff in staff_list:
                weekends = schedule.count_weekend_shifts(staff.identifier)
                effective_nights = schedule.count_effective_nights(staff.identifier, staff)
                total_notdienst = weekends + effective_nights  # Combined metric
                
                # FTE Scaling (normalized to 40h)
                if staff.hours > 0:
                    total_notdienst_fte = (total_notdienst / staff.hours) * 40
                else:
                    total_notdienst_fte = 0.0
                
                staff_stats.append({
                    "Name": staff.name,
                    "Kürzel": staff.identifier,
                    "Beruf": staff.beruf.value,
                    "Abteilung": staff.abteilung.value,
                    "Stunden": staff.hours,
                    "ND möglich": "✅" if staff.nd_possible else "❌",
                    "WE (Abs)": weekends,
                    "Nächte (Eff)": effective_nights,
                    "Notdienst Gesamt": total_notdienst,
                    "Notdienst / 40h": round(total_notdienst_fte, 2),
                })
            
            df_stats = pd.DataFrame(staff_stats)
            
            # ========== FAIRNESS CHECK PER GROUP ==========
            # Check for unfair distribution WITHIN each job group (threshold: 2+ normalized shifts)
            fairness_issues: list[dict] = []
            for beruf in [Beruf.TFA, Beruf.AZUBI, Beruf.INTERN]:
                group_df = df_stats[df_stats["Beruf"] == beruf.value]
                if len(group_df) < 2:
                    continue
                
                group_mean = group_df["Notdienst / 40h"].mean()
                for _, row in group_df.iterrows():
                    deviation = row["Notdienst / 40h"] - group_mean
                    if abs(deviation) >= 2.0:  # Threshold: 2+ normalized shifts
                        fairness_issues.append({
                            "name": row["Name"],
                            "kuerzel": row["Kürzel"],
                            "beruf": beruf.value,
                            "value": row["Notdienst / 40h"],
                            "group_mean": group_mean,
                            "deviation": deviation,
                            "status": "overburdened" if deviation > 0 else "underburdened",
                        })
            
            # Display fairness warning with specific names
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
            
            # ========== KEY METRICS ==========
            st.markdown("#### 📊 Übersicht")
            
            # Fairness KPIs
            notdienst_values = df_stats["Notdienst / 40h"].values
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("Ø Notdienst / 40h", f"{notdienst_values.mean():.2f}")
            with col_m2:
                st.metric("Std. Abweichung", f"{notdienst_values.std():.2f}", help="Niedriger = fairer")
            with col_m3:
                st.metric("Min", f"{notdienst_values.min():.2f}")
            with col_m4:
                st.metric("Max", f"{notdienst_values.max():.2f}")

            # ========== DETAILED TABLES BY GROUP ==========
            st.markdown("---")
            st.markdown("#### 📋 Detailansicht nach Berufsgruppe")
            st.caption("Farbkodierung: 🟢 Grün = unterdurchschnittlich, 🟡 Gelb = durchschnittlich, 🔴 Rot = überdurchschnittlich (relativ zur Gruppe)")
            
            def style_group_table(df: pd.DataFrame, group_mean: float) -> pd.DataFrame:
                """Apply red/yellow/green styling based on deviation from group mean."""
                def color_notdienst(val: float) -> str:
                    deviation = val - group_mean
                    if deviation >= 1.5:
                        return "background-color: #ffcccc"  # Red - overburdened
                    elif deviation <= -1.5:
                        return "background-color: #ccffcc"  # Green - underburdened
                    else:
                        return "background-color: #ffffcc"  # Yellow - normal
                
                return df.style.applymap(
                    color_notdienst, subset=["Notdienst / 40h"]
                ).format({"Nächte (Eff)": "{:.1f}", "Notdienst Gesamt": "{:.1f}"})
            
            # TFA Table
            df_tfa = df_stats[df_stats["Beruf"] == "TFA"].copy()
            if not df_tfa.empty:
                tfa_mean = df_tfa["Notdienst / 40h"].mean()
                st.markdown(f"##### 👩‍⚕️ TFA ({len(df_tfa)} Mitarbeiter, Ø {tfa_mean:.2f} Notdienst/40h)")
                st.dataframe(
                    style_group_table(df_tfa, tfa_mean),
                    use_container_width=True,
                    height=min(400, 35 * len(df_tfa) + 38),
                )
            
            # Azubi Table
            df_azubi = df_stats[df_stats["Beruf"] == "Azubi"].copy()
            if not df_azubi.empty:
                azubi_mean = df_azubi["Notdienst / 40h"].mean()
                st.markdown(f"##### 🎓 Azubi ({len(df_azubi)} Mitarbeiter, Ø {azubi_mean:.2f} Notdienst/40h)")
                st.dataframe(
                    style_group_table(df_azubi, azubi_mean),
                    use_container_width=True,
                    height=min(400, 35 * len(df_azubi) + 38),
                )
            
            # Intern Table
            df_intern = df_stats[df_stats["Beruf"] == "Intern"].copy()
            if not df_intern.empty:
                intern_mean = df_intern["Notdienst / 40h"].mean()
                st.markdown(f"##### 🩺 Intern ({len(df_intern)} Mitarbeiter, Ø {intern_mean:.2f} Notdienst/40h)")
                st.dataframe(
                    style_group_table(df_intern, intern_mean),
                    use_container_width=True,
                    height=min(400, 35 * len(df_intern) + 38),
                )

            # ========== GROUP COMPARISON ==========
            st.markdown("---")
            st.markdown("#### 👥 Gruppen-Vergleich")
            
            group_stats = df_stats.groupby("Beruf").agg({
                "Notdienst / 40h": ["count", "mean", "std", "min", "max"],
                "WE (Abs)": "sum",
                "Nächte (Eff)": "sum",
            }).round(2)
            
            # Flatten column names
            group_stats.columns = [
                "Anzahl MA", "Ø Notdienst/40h", "Std.Abw.", "Min", "Max",
                "WE Gesamt", "Nächte Gesamt"
            ]
            group_stats["Spread"] = group_stats["Max"] - group_stats["Min"]
            
            st.dataframe(group_stats, use_container_width=True)
            
            # ========== OUTLIERS / ACTIONABLE INSIGHTS ==========
            st.markdown("---")
            st.markdown("#### 🎯 Handlungsempfehlungen")
            
            # Find intra-group outliers (focus on within-group fairness)
            recommendations = []
            for beruf in [Beruf.TFA, Beruf.AZUBI, Beruf.INTERN]:
                group_df = df_stats[df_stats["Beruf"] == beruf.value]
                if len(group_df) < 2:
                    continue
                
                group_mean = group_df["Notdienst / 40h"].mean()
                group_std = group_df["Notdienst / 40h"].std()
                group_spread = group_df["Notdienst / 40h"].max() - group_df["Notdienst / 40h"].min()
                
                # Flag groups with high internal spread (>3.0)
                if group_spread > 3.0:
                    high_load = group_df[group_df["Notdienst / 40h"] > group_mean + 1.5]
                    low_load = group_df[group_df["Notdienst / 40h"] < group_mean - 1.5]
                    
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
                    st.markdown(f"""
                    **{rec['group']}** (Spread: {rec['spread']:.2f}):
                    - Überlastet: {rec['high_load']}
                    - Unterlastet: {rec['low_load']}
                    """)
            else:
                st.success("✅ Alle Gruppen haben eine ausgewogene interne Verteilung (Spread ≤ 3.0).")
            
            # Breakdown explanation
            with st.expander("ℹ️ Berechnungslogik"):
                st.markdown(r"""
                **Notdienst Gesamt** = Wochenend-Schichten + Effektive Nächte
                
                - **Wochenend-Schichten**: Jede WE-Schicht zählt 1×
                - **Effektive Nächte**: 
                  - TFA/Intern: Paar-Nacht = 0.5×, Solo-Nacht = 1.0×
                  - Azubi: Immer 1.0× (auch bei Paarung)
                
                **FTE-Normalisierung**: $\frac{\text{Notdienst Gesamt}}{\text{Vertragsstunden}} \times 40$
                
                **Fairness-Schwellwert**: Eine Abweichung von ≥2.0 normalisierte Schichten 
                vom Gruppendurchschnitt wird als unfair markiert.
                
                **Farbkodierung**: Vergleich mit dem Durchschnitt der eigenen Berufsgruppe:
                - 🔴 Rot: ≥1.5 über Durchschnitt
                - 🟡 Gelb: Innerhalb ±1.5
                - 🟢 Grün: ≥1.5 unter Durchschnitt
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
                "Min Consecutive Nights": "TFA/Interns: mind. 2 aufeinanderfolgende Nächte",
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

    st.markdown("### Dienstplan exportieren")

    # Prepare export data
    assignment_data = []
    for assignment in sorted(schedule.assignments, key=lambda a: a.shift.shift_date):
        assignment_data.append(
            {
                "Datum": assignment.shift.shift_date.strftime("%d.%m.%Y"),
                "Wochentag": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][
                    assignment.shift.shift_date.weekday()
                ],
                "Schicht": assignment.shift.shift_type.value,
                "Mitarbeiter": assignment.staff_identifier,
                "Paarweise": "Ja" if assignment.is_paired else "Nein",
            }
        )

    df_export = pd.DataFrame(assignment_data)

    # CSV download
    csv_buffer = io.StringIO()
    df_export.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    csv_data = csv_buffer.getvalue()

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Als CSV herunterladen",
            data=csv_data,
            file_name=f"dienstplan_{schedule.quarter_start.strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            width="content",
        )

    with col2:
        # Excel download
        excel_buffer = io.BytesIO()
        df_export.to_excel(excel_buffer, index=False, engine="xlsxwriter")
        excel_data = excel_buffer.getvalue()

        st.download_button(
            label="📥 Als Excel herunterladen",
            data=excel_data,
            file_name=f"dienstplan_{schedule.quarter_start.strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="content",
        )

    # Preview
    st.markdown("---")
    st.markdown("### Vorschau")
    st.dataframe(df_export, width="content", height=600)


if __name__ == "__main__":
    main()
