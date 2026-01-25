"""Streamlit app for Notdienst scheduling."""

import io
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from scheduler.models import Beruf, Staff, load_staff_from_csv
from scheduler.solver import generate_schedule
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
            st.dataframe(df, use_container_width=True)

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
    st.dataframe(df, use_container_width=True, height=600)

    # Statistics
    st.markdown("---")
    st.markdown("### Statistik")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("TFA", sum(1 for s in staff_list if s.beruf == Beruf.TFA))
    with col2:
        st.metric("Azubi", sum(1 for s in staff_list if s.beruf == Beruf.AZUBI))
    with col3:
        st.metric("TA", sum(1 for s in staff_list if s.beruf == Beruf.TA))
    with col4:
        st.metric("Gesamt", len(staff_list))


def page_regeln() -> None:
    """Page: Display constraint rules."""
    st.title("📋 Regeln & Constraints")

    st.markdown("""
    ## Hard Constraints (müssen erfüllt sein)

    ### Wochenend-Schichten
    - **Samstag 10-19**: Nur Azubis mit `reception=False`
    - **Samstag 10-21**: Azubis mit `reception=True` oder TFA
    - **Sonntag 8-20:30**: Nur erwachsene Azubis (≥18 Jahre)
    - **Minderjährige**: Dürfen **nicht** sonntags arbeiten
    - **TAs**: Arbeiten **nie** am Wochenende

    ### Nachtdienste
    - **Sonntag→Montag**: 1 TFA (TA vor Ort)
    - **Montag→Dienstag**: 1 TFA (TA vor Ort)
    - **Andere Nächte**: 1-2 TFA
    - **Azubis**: Arbeiten **nie** alleine nachts
    - **Pairing**: Mitarbeiter mit `nd_alone=False` müssen paarweise arbeiten (außer So→Mo, Mo→Di mit TA)
    - **TAs**: Arbeiten 2 Nächte/Monat (alleine, So→Mo & Mo→Di)

    ### Zeitliche Constraints
    - **3-Wochen-Regel**: Max. 1 zusammenhängender Schichtblock pro 3-Wochen-Fenster
    - **Nacht/Tag-Konflikt**: Kein Tagdienst am selben oder nächsten Tag nach Nachtschicht
    - **nd_count**: Anzahl aufeinanderfolgender Nächte muss in `nd_count` enthalten sein
    - **nd_exceptions**: Keine Nächte an Wochentagen in `nd_exceptions` (1=Mo, 7=So)

    ## Soft Constraints (Optimierungsziele)

    ### Faire Verteilung
    - **Proportional**: Notdienste proportional zu Wochenstunden
    - **Effective Nights**: Paar-Nächte zählen 0,5× pro Person
    - **Gruppen-Fairness**: Minimale Abweichung innerhalb TFA/Azubi/TA
    - **Minderjährige**: Erhalten mehr Samstage (Ausgleich für keine Sonntage)

    ### Penalty-System
    - Abweichung von Ziel → Quadratische Strafe
    - Ungleichheit in Gruppe → Standardabweichung × 10
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
    col1, col2 = st.columns(2)
    with col1:
        max_iterations = st.number_input(
            "Max. Iterationen", min_value=100, max_value=10000, value=2000, step=100
        )
    with col2:
        random_seed = st.number_input(
            "Random Seed (optional)", min_value=0, max_value=9999, value=42, step=1
        )

    # Generate button
    st.markdown("---")
    if st.button("🚀 Plan generieren", type="primary", use_container_width=True):
        with st.spinner("⏳ Generiere Dienstplan..."):
            try:
                staff_list: list[Staff] = st.session_state.staff_list
                result = generate_schedule(
                    staff_list,
                    quarter_start,
                    max_iterations=max_iterations,
                    random_seed=random_seed,
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
    """Page: Display generated schedule."""
    st.title("📅 Plan anzeigen")

    if st.session_state.schedule is None:
        st.warning("⚠️ Bitte zuerst einen Plan erstellen (Seite 'Plan erstellen')")
        return

    schedule = st.session_state.schedule
    staff_list: list[Staff] = st.session_state.staff_list
    validation = st.session_state.validation_result

    # Validation status
    if validation:
        if validation.is_valid():
            st.success(f"✅ Plan ist gültig (Soft Penalty: {validation.soft_penalty:.2f})")
        else:
            st.error(f"❌ Plan verletzt {len(validation.hard_violations)} Hard Constraints")
            with st.expander("Constraint-Verletzungen anzeigen"):
                for violation in validation.hard_violations[:20]:
                    st.text(f"• {violation}")

    # Statistics
    st.markdown("### Statistik")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Zuweisungen gesamt", len(schedule.assignments))
    with col2:
        weekend_count = sum(1 for a in schedule.assignments if a.shift.is_weekend_shift())
        st.metric("Wochenend-Schichten", weekend_count)
    with col3:
        night_count = sum(1 for a in schedule.assignments if a.shift.is_night_shift())
        st.metric("Nachtdienste", night_count)
    with col4:
        st.metric("Zeitraum", f"{(schedule.quarter_end - schedule.quarter_start).days} Tage")

    # Per-staff counters
    st.markdown("---")
    st.markdown("### Notdienste pro Mitarbeiter")

    staff_stats = []
    for staff in staff_list:
        weekends = schedule.count_weekend_shifts(staff.identifier)
        effective_nights = schedule.count_effective_nights(staff.identifier)
        total = weekends + effective_nights

        staff_stats.append(
            {
                "Name": staff.name,
                "Kürzel": staff.identifier,
                "Beruf": staff.beruf.value,
                "Stunden": staff.hours,
                "Wochenenden": weekends,
                "Effective Nächte": f"{effective_nights:.1f}",
                "Gesamt": f"{total:.1f}",
            }
        )

    df_stats = pd.DataFrame(staff_stats)
    st.dataframe(df_stats, use_container_width=True, height=400)

    # Assignment table
    st.markdown("---")
    st.markdown("### Alle Zuweisungen")

    assignment_data = []
    for assignment in sorted(schedule.assignments, key=lambda a: a.shift.shift_date):
        assignment_data.append(
            {
                "Datum": assignment.shift.shift_date.strftime("%d.%m.%Y"),
                "Schicht": assignment.shift.shift_type.value,
                "Mitarbeiter": assignment.staff_identifier,
                "Paar": "Ja" if assignment.is_paired else "Nein",
            }
        )

    df_assignments = pd.DataFrame(assignment_data)
    st.dataframe(df_assignments, use_container_width=True, height=600)

    # Manual override placeholder
    st.markdown("---")
    st.markdown("### Manuelle Anpassungen")
    st.info("ℹ️ Manuelle Überarbeitung wird in einer zukünftigen Version verfügbar sein.")


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
            use_container_width=True,
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
            use_container_width=True,
        )

    # Preview
    st.markdown("---")
    st.markdown("### Vorschau")
    st.dataframe(df_export, use_container_width=True, height=600)


if __name__ == "__main__":
    main()
