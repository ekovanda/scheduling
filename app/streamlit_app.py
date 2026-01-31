"""Streamlit app for Notdienst scheduling."""

import io
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from scheduler.models import Beruf, ShiftType, Staff, load_staff_from_csv
from scheduler.solver import SolverBackend, generate_schedule
from scheduler.validator import validate_schedule

# Page config
st.set_page_config(page_title="Dienstplan Generator", page_icon="📅", layout="wide")


def main() -> None:
    """Main app entry point."""
    # Initialize session state
    if "staff_list" not in st.session_state:
        st.session_state.staff_list = None
    if "schedule" not in st.session_state:
        st.session_state.schedule = None
    if "validation_result" not in st.session_state:
        st.session_state.validation_result = None

    # Sidebar navigation
    st.sidebar.title("📅 Dienstplan Generator")
    page = st.sidebar.radio(
        "Navigation",
        [
            "Laden / CSV",
            "Personal",
            "Regeln",
            "Plan erstellen",
            "Plan anzeigen",
            "Export",
        ],
    )

    # Route to pages
    if page == "Laden / CSV":
        page_load_csv()
    elif page == "Personal":
        page_personal()
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

    # Placeholder for vacation data
    st.markdown("---")
    st.markdown("### Urlaub / Verfügbarkeit hochladen")
    st.file_uploader(
        "CSV-Datei mit Urlaubsdaten (optional)",
        type=["csv"],
        key="vacation_upload",
        disabled=True,
    )
    st.info("ℹ️ Diese Funktion wird in einer zukünftigen Version verfügbar sein.")

    # Show current status
    st.markdown("---")
    if st.session_state.staff_list:
        st.success(f"📊 Status: {len(st.session_state.staff_list)} Mitarbeiter geladen")
    else:
        st.warning("⚠️ Noch keine Personaldaten geladen")


def page_personal() -> None:
    """Page: View and filter staff data."""
    st.title("👥 Personal")

    if st.session_state.staff_list is None:
        st.warning("⚠️ Bitte zuerst Personaldaten laden (Seite 'Laden / CSV')")
        return

    staff_list: list[Staff] = st.session_state.staff_list

    # Filters
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
    - **Sonntag 8-20:30**: Nur erwachsene Azubis (≥18 Jahre)
    - **Minderjährige**: Dürfen **nicht** sonntags arbeiten
    - **Interns**: Arbeiten **nie** am Wochenende
    - **Max. 1 Schicht/Tag**: Jede Person kann max. 1 Schicht pro Tag haben

    ### Nachtdienste
    - **Alle Nächte**: 1-2 Personen, mind. 1 nicht-Azubi (TFA oder Intern)
    - **Sonntag→Montag / Montag→Dienstag**: Intern vor Ort, optional +1 Azubi
    - **Azubis**: Müssen **immer** mit einem TFA oder Intern zusammenarbeiten
    - **Zwei Azubis**: Können **nie** zusammen Nachtdienst machen
    - **nd_alone=False**: Mitarbeiter müssen paarweise arbeiten (außer So→Mo, Mo→Di)
    - **nd_alone=True**: Mitarbeiter arbeiten **alleine** (keine Paarung)
    - **Min. 2 Nächte**: TFA und Interns müssen mind. 2 aufeinanderfolgende Nächte arbeiten
    - **Interns**: Arbeiten 2-3 Nächte/Monat (6-9 pro Quartal)

    ### Zeitliche Constraints
    - **2-Wochen-Regel**: Max. 1 zusammenhängender Schichtblock pro 2-Wochen-Fenster
    - **Nacht/Tag-Konflikt**: Kein Tagdienst am selben oder nächsten Tag nach Nachtschicht
    - **nd_exceptions**: Keine Nächte an Wochentagen in `nd_exceptions` (1=Mo, 7=So)

    ## Soft Constraints (Optimierungsziele)

    - **nd_max_consecutive**: Max. aufeinanderfolgende Nächte (wird möglichst eingehalten)
    - **Faire Verteilung**: Notdienste (WE + Nächte kombiniert) proportional zu Wochenstunden
    - **Effective Nights**: Paar-Nächte zählen 0,5× pro Person, Solo-Nächte 1,0×
    - **Gruppen-Fairness**: Minimale Abweichung (±1-2) innerhalb TFA/Azubi/Intern

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

    # Generate button
    st.markdown("---")
    if st.button("🚀 Plan generieren", type="primary", width="content"):
        spinner_msg = "⏳ Generiere Dienstplan mit CP-SAT..." if solver_backend == SolverBackend.CPSAT else "⏳ Generiere Dienstplan..."
        with st.spinner(spinner_msg):
            try:
                staff_list: list[Staff] = st.session_state.staff_list
                result = generate_schedule(
                    staff_list,
                    quarter_start,
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
            shift_map[key].append(assignment.staff_identifier)

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
        st.markdown("### Fairness-Analyse (FTE skalierte Metriken)")
        st.markdown(r"Die Metriken sind auf `40h` Vollzeit skaliert: $\text{FTE-Score} = \frac{\text{Anzahl}}{\text{Stunden}} \times 40$")
        
        if staff_list:
            staff_stats = []
            for staff in staff_list:
                # Raw counts
                weekends = schedule.count_weekend_shifts(staff.identifier)
                effective_nights = schedule.count_effective_nights(staff.identifier)
                
                # FTE Scaling
                if staff.hours > 0:
                    weekend_fte = (weekends / staff.hours) * 40
                    night_fte = (effective_nights / staff.hours) * 40
                else:
                    weekend_fte = 0
                    night_fte = 0
                
                staff_stats.append(
                    {
                        "Name": staff.name,
                        "Beruf": staff.beruf.value,
                        "Stunden": staff.hours,
                        "ND möglich": staff.nd_possible,  # Track eligibility
                        # Raw
                        "Wochenenden (Abs)": weekends,
                        "Nächte (Eff)": effective_nights,
                        # FTE Normalized
                        "WE / 40h": round(weekend_fte, 2),
                        "Nacht / 40h": round(night_fte, 2) if staff.nd_possible else None,  # Exclude ineligible
                    }
                )

            df_stats = pd.DataFrame(staff_stats)
            
            # 1. Detailed Table with Heatmap
            st.markdown("#### Detailansicht")
            st.caption("💡 Mitarbeiter mit `ND möglich = False` werden bei der Nacht-Fairness nicht gewertet (vertragliche Regelung).")
            st.dataframe(
                df_stats.style.background_gradient(subset=["WE / 40h", "Nacht / 40h"], cmap="YlOrRd"), 
                use_container_width=True, 
                height=400
            )

            # 2. Grouped Summary - SEPARATE for weekends and nights
            st.markdown("#### Gruppen-Vergleich (FTE-normalisiert)")
            
            # Weekend stats: Include everyone
            st.markdown("**Wochenenden** (alle Mitarbeiter)")
            weekend_grouped = df_stats.groupby("Beruf")["WE / 40h"]
            weekend_summary = weekend_grouped.agg(["count", "mean", "std", "min", "max"])
            weekend_summary["range"] = weekend_summary["max"] - weekend_summary["min"]
            st.dataframe(weekend_summary, use_container_width=True)
            
            # Night stats: Only include staff with nd_possible=True
            st.markdown("**Nachtdienste** (nur Mitarbeiter mit `ND möglich = True`)")
            df_nd_eligible = df_stats[df_stats["ND möglich"] == True].copy()
            if not df_nd_eligible.empty:
                night_grouped = df_nd_eligible.groupby("Beruf")["Nacht / 40h"]
                night_summary = night_grouped.agg(["count", "mean", "std", "min", "max"])
                night_summary["range"] = night_summary["max"] - night_summary["min"]
                st.dataframe(night_summary, use_container_width=True)
            else:
                st.info("Keine Mitarbeiter mit Nachtdienst-Berechtigung.")

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
                "Min Consecutive Nights": "TFA/Interns: mind. 2 aufeinanderfolgende Nächte",
                "Night/Day Conflict": "Ruhezeiten: Kein Tagdienst an/nach Nachtdienst",
                "2-Week Block Limit": "Max. 1 Block pro 2 Wochen",
                "ND Exception Weekday": "Beachtung blockierter Wochentage (nd_exceptions)",
                "Shift Eligibility": "Qualifikation für Schicht",
                "Shift Coverage": "Mindestbesetzung (Nachts)",
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
