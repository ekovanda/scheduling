"""Export service for converting schedule documents to styled Excel workbooks and CSV."""

import csv
import io
from typing import Any

import pandas as pd

from app.persistence.models import QuarterScheduleDocument, StaffMember


def export_schedule_to_csv(doc: QuarterScheduleDocument) -> str:
    """Export schedule assignments to standard UTF-8 CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Wochentag",
            "Datum",
            "Mitarbeiter",
            "Schicht",
            "Paarweise",
            "Geplant",
            "Status",
            "Begruendung",
        ]
    )

    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    sorted_assignments = sorted(doc.assignments, key=lambda a: (a.shift_date, a.shift_type.value))

    for a in sorted_assignments:
        wt = weekday_names[a.shift_date.weekday()]
        dt = a.shift_date.strftime("%d.%m.%Y")
        status_label = "Tausch/Vertretung" if a.is_override else "Original"
        reason = a.override_reason or ""
        writer.writerow(
            [
                wt,
                dt,
                a.actual_staff_id,
                a.shift_type.value,
                "Ja" if a.is_paired else "Nein",
                a.planned_staff_id,
                status_label,
                reason,
            ]
        )

    return output.getvalue()


def export_schedule_to_excel(
    doc: QuarterScheduleDocument,
    staff_map: dict[str, StaffMember] | None = None,
) -> bytes:
    """Export schedule document to styled Excel workbook (.xlsx).

    Generates:
    - Sheet 1: 'Nachtdienste' (Night shifts)
    - Sheet 2: 'Wochenenddienste' (Day weekend shifts)
    - Sheet 3: 'Schichtverteilung' (Shift count summary per employee)
    """
    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    staff_map = staff_map or {}

    rows: list[dict[str, Any]] = []
    staff_counts: dict[str, dict[str, int]] = {}

    for a in sorted(doc.assignments, key=lambda x: (x.shift_date, x.shift_type.value)):
        staff_display = a.actual_staff_id
        if a.actual_staff_id in staff_map:
            staff_display = f"{staff_map[a.actual_staff_id].name} ({a.actual_staff_id})"

        is_night = a.shift_type.value.startswith("N_")
        shift_category = "Nacht" if is_night else "Wochenende"

        if a.actual_staff_id not in staff_counts:
            staff_counts[a.actual_staff_id] = {"Nacht": 0, "Wochenende": 0, "Gesamt": 0}
        staff_counts[a.actual_staff_id][shift_category] += 1
        staff_counts[a.actual_staff_id]["Gesamt"] += 1

        status_text = f"Tausch: {a.override_reason}" if a.is_override else "Original"

        rows.append(
            {
                "Wochentag": weekday_names[a.shift_date.weekday()],
                "Datum": a.shift_date.strftime("%d.%m.%Y"),
                "Mitarbeiter": staff_display,
                "Schicht": a.shift_type.value,
                "Paarweise": "Ja" if a.is_paired else "Nein",
                "Geplant": a.planned_staff_id,
                "Status": status_text,
                "is_night": is_night,
            }
        )

    df_all = pd.DataFrame(rows) if rows else pd.DataFrame()

    if not df_all.empty:
        df_nights = df_all[df_all["is_night"]].drop(columns=["is_night"]).reset_index(drop=True)
        df_weekends = df_all[~df_all["is_night"]].drop(columns=["is_night"]).reset_index(drop=True)
    else:
        df_nights = pd.DataFrame(
            columns=[
                "Wochentag",
                "Datum",
                "Mitarbeiter",
                "Schicht",
                "Paarweise",
                "Geplant",
                "Status",
            ]
        )
        df_weekends = pd.DataFrame(
            columns=[
                "Wochentag",
                "Datum",
                "Mitarbeiter",
                "Schicht",
                "Paarweise",
                "Geplant",
                "Status",
            ]
        )

    # Summary table
    summary_rows = []
    for s_id, counts in sorted(staff_counts.items()):
        name = staff_map[s_id].name if s_id in staff_map else s_id
        summary_rows.append(
            {
                "Kuerzel": s_id,
                "Name": name,
                "Nachtdienste": counts["Nacht"],
                "Wochenenddienste": counts["Wochenende"],
                "Gesamtdienste": counts["Gesamt"],
            }
        )
    df_summary = pd.DataFrame(summary_rows) if summary_rows else pd.DataFrame()

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_nights.to_excel(writer, sheet_name="Nachtdienste", index=False)
        df_weekends.to_excel(writer, sheet_name="Wochenenddienste", index=False)
        if not df_summary.empty:
            df_summary.to_excel(writer, sheet_name="Schichtverteilung", index=False)

        workbook = writer.book
        header_format = workbook.add_format(
            {
                "bold": True,
                "text_wrap": True,
                "valign": "top",
                "fg_color": "#1E3A8A",
                "font_color": "#FFFFFF",
                "border": 1,
            }
        )
        cell_format = workbook.add_format({"border": 1, "valign": "vcenter"})

        for sheet_name, df_sheet in [
            ("Nachtdienste", df_nights),
            ("Wochenenddienste", df_weekends),
            ("Schichtverteilung", df_summary),
        ]:
            if sheet_name not in writer.sheets:
                continue
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)

            for col_num, col_name in enumerate(df_sheet.columns):
                worksheet.write(0, col_num, col_name, header_format)
                max_len = max(
                    df_sheet[col_name].astype(str).map(len).max() if not df_sheet.empty else 0,
                    len(str(col_name)),
                )
                worksheet.set_column(col_num, col_num, max(max_len + 3, 12), cell_format)

    return buffer.getvalue()
