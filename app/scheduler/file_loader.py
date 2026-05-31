"""Flexible, lenient file parsing for CSV and XLSX formats.

Supports:
- CSV and XLSX file formats
- Fuzzy column name matching (e.g., "Name", "name", "Name/Kürzel" all map to 'name')
- Case-insensitive column headers
- Optional columns with sensible defaults
- Better error messages
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

T = TypeVar("T")


class ColumnMappingError(Exception):
    """Raised when required columns cannot be found in the file."""

    pass


class FileFormatError(Exception):
    """Raised when file format is not supported."""

    pass


def _normalize_column_name(col: str) -> str:
    """Normalize a column name for comparison.

    Converts to lowercase, strips whitespace, removes common splits.
    E.g., "Name / Kürzel" -> "namekürzel"
    """
    return col.lower().strip().replace(" / ", "").replace("/", "").replace(" ", "")


def _find_column(df: pd.DataFrame, possible_names: list[str]) -> str:
    """Find a column in DataFrame matching any of the possible names (case-insensitive).

    Args:
        df: DataFrame to search
        possible_names: List of column names to try

    Returns:
        The actual column name in the DataFrame

    Raises:
        ColumnMappingError: If no matching column found
    """
    normalized_possible = [_normalize_column_name(n) for n in possible_names]

    for actual_col in df.columns:
        normalized_actual = _normalize_column_name(actual_col)
        if normalized_actual in normalized_possible:
            return actual_col

    raise ColumnMappingError(
        f"Could not find column matching any of {possible_names}. "
        f"Available columns: {list(df.columns)}"
    )


def _safe_get_value(row: dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely extract a value from a row dict, returning default if missing or empty."""
    value = row.get(key)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    return value


def load_file_to_dataframe(file_path: Path | str) -> pd.DataFrame:
    """Load a CSV or XLSX file into a DataFrame.

    Args:
        file_path: Path to CSV or XLSX file

    Returns:
        pandas DataFrame

    Raises:
        FileFormatError: If file format is not supported
    """
    file_path = Path(file_path) if isinstance(file_path, str) else file_path
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(file_path, dtype=str)
    elif suffix in [".xlsx", ".xls"]:
        return pd.read_excel(file_path, dtype=str)
    else:
        raise FileFormatError(f"Unsupported file format: {suffix}. Use .csv or .xlsx")


def _parse_available_from(value: Any, identifier: str) -> date | None:
    """Parse the available_from field from a staff row.

    Accepts DD.MM.YYYY format.  Empty/None values return None.

    Raises:
        ValueError: If the value is present but cannot be parsed.
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    raw = str(value).strip()
    # Try the canonical user-facing format first, then the format Excel/pandas
    # produces when a cell is formatted as "Date" (e.g. '2026-08-01 00:00:00').
    for fmt in ("%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Invalid available_from format for '{identifier}': '{raw}'. "
        "Expected DD.MM.YYYY (e.g. 01.07.2026)."
    )


def load_staff_from_file(file_path: Path | str) -> dict[str, dict[str, Any]]:
    """Load staff data from CSV or XLSX file.

    Returns a dict mapping identifier -> staff_data_dict for flexible ingestion.
    Handles flexible column names and formats.

    Args:
        file_path: Path to CSV or XLSX file
        Expected columns (flexible names):
            - name/Name/Name des Mitarbeiters
            - identifier/Kürzel/ID
            - adult/Alter/Age
            - hours/Stunden/Vertragsstunden/Hours
            - beruf/Beruf/Role/Profession (TFA, Azubi, Intern)
            - abteilung/Department/Abt. (optional)
            - reception/Anmeldung/Reception
            - nd_possible/Nacht_möglich/Can_work_nights
            - nd_alone/Nacht_alleine/Night_alone
            - nd_max_consecutive/Max_Nächte/Max_consecutive_nights (optional)
            - nd_min_consecutive/Min_Nächte/Min_consecutive_nights (optional)
            - nd_exceptions/Blockierte_Wochentage/Night_exceptions (optional, JSON array)
            - birthday/Geburtstag/Birthday (optional, MM-DD format)

    Returns:
        Dict mapping identifier -> staff record

    Raises:
        ColumnMappingError: If required columns cannot be found
        ValueError: If data validation fails
    """
    df = load_file_to_dataframe(file_path)

    # Find columns (with fallback alternatives)
    col_name = _find_column(df, ["name", "Name", "Name des Mitarbeiters"])
    col_id = _find_column(df, ["identifier", "kürzel", "Kürzel", "id", "ID", "staff_id"])
    col_adult = _find_column(df, ["adult", "Adult", "Alter", "Age", "alter"])
    col_hours = _find_column(
        df, ["hours", "Hours", "Stunden", "Vertragsstunden", "wöchentliche_Stunden"]
    )
    col_beruf = _find_column(df, ["beruf", "Beruf", "Role", "Profession", "profession"])
    col_reception = _find_column(
        df, ["reception", "Reception", "Anmeldung", "can_reception", "reception_capable"]
    )
    col_nd_possible = _find_column(
        df, ["nd_possible", "nacht_möglich", "Nacht_möglich", "can_work_nights", "nd_capable"]
    )
    col_nd_alone = _find_column(
        df, ["nd_alone", "nacht_alleine", "Nacht_alleine", "night_alone", "solo_nights"]
    )

    # Optional columns
    col_abteilung = None
    try:
        col_abteilung = _find_column(df, ["abteilung", "Abteilung", "department", "Department"])
    except ColumnMappingError:
        pass

    col_nd_max = None
    try:
        col_nd_max = _find_column(
            df,
            [
                "nd_max_consecutive",
                "max_nächte",
                "Max_Nächte",
                "max_consecutive_nights",
            ],
        )
    except ColumnMappingError:
        pass

    col_nd_min = None
    try:
        col_nd_min = _find_column(
            df, ["nd_min_consecutive", "min_nächte", "Min_Nächte", "min_consecutive_nights"]
        )
    except ColumnMappingError:
        pass

    col_nd_exceptions = None
    try:
        col_nd_exceptions = _find_column(
            df,
            ["nd_exceptions", "blockierte_wochentage", "Blockierte_Wochentage", "night_exceptions"],
        )
    except ColumnMappingError:
        pass

    col_birthday = None
    try:
        col_birthday = _find_column(df, ["birthday", "Geburtstag", "geburtstag", "Birth"])
    except ColumnMappingError:
        pass

    col_available_from = None
    try:
        col_available_from = _find_column(
            df, ["available_from", "Verfügbar_ab", "verfügbar_ab", "Verfuegbar_ab"]
        )
    except ColumnMappingError:
        pass

    # Parse rows
    staff_dict: dict[str, dict[str, Any]] = {}

    for _, row in df.iterrows():
        identifier = _safe_get_value(row, col_id)
        if not identifier:
            raise ValueError(f"Found row with missing identifier: {row.to_dict()}")

        # Convert boolean strings
        def parse_bool(val: Any) -> bool:
            if val is None or (isinstance(val, str) and val.strip() == ""):
                return False
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ["true", "ja", "yes", "1", "y", "j"]
            return bool(val)

        # Convert hours to int
        hours_val = _safe_get_value(row, col_hours)
        try:
            hours = int(float(hours_val)) if hours_val else 0
        except (ValueError, TypeError):
            raise ValueError(f"Invalid hours value for {identifier}: {hours_val}")

        # Parse nd_exceptions (JSON array or comma-separated)
        nd_exceptions_raw = _safe_get_value(row, col_nd_exceptions)
        nd_exceptions: list[int] = []
        if nd_exceptions_raw:
            try:
                if isinstance(nd_exceptions_raw, str):
                    if nd_exceptions_raw.strip().startswith("["):
                        nd_exceptions = json.loads(nd_exceptions_raw)
                    else:
                        # Try comma-separated
                        nd_exceptions = [int(x.strip()) for x in nd_exceptions_raw.split(",")]
                else:
                    nd_exceptions = list(nd_exceptions_raw)
            except (json.JSONDecodeError, ValueError) as e:
                raise ValueError(
                    f"Invalid nd_exceptions format for {identifier}: {nd_exceptions_raw}. "
                    f"Expected JSON array or comma-separated integers."
                ) from e

        staff_dict[identifier] = {
            "name": _safe_get_value(row, col_name) or identifier,
            "identifier": identifier,
            "adult": parse_bool(_safe_get_value(row, col_adult)),
            "hours": hours,
            "beruf": (_safe_get_value(row, col_beruf) or "TFA").strip(),
            "abteilung": _safe_get_value(row, col_abteilung, "other"),
            "reception": parse_bool(_safe_get_value(row, col_reception)),
            "nd_possible": parse_bool(_safe_get_value(row, col_nd_possible)),
            "nd_alone": parse_bool(_safe_get_value(row, col_nd_alone)),
            "nd_max_consecutive": (
                int(_safe_get_value(row, col_nd_max)) if _safe_get_value(row, col_nd_max) else None
            ),
            "nd_min_consecutive": (
                int(_safe_get_value(row, col_nd_min)) if _safe_get_value(row, col_nd_min) else 2
            ),
            "nd_exceptions": nd_exceptions,
            "birthday": _safe_get_value(row, col_birthday),
            "available_from": _parse_available_from(
                _safe_get_value(row, col_available_from), identifier
            ) if col_available_from else None,
        }

    return staff_dict


def load_vacations_from_file(file_path: Path | str) -> dict[str, list[dict[str, Any]]]:
    """Load vacation data from CSV or XLSX file.

    Returns dict mapping identifier -> list of vacation periods.
    Handles flexible column names and date formats.

    Args:
        file_path: Path to CSV or XLSX file
        Expected columns (flexible names):
            - identifier/Mitarbeiter/Staff/Kürzel
            - start_date/Startdatum/Von/From/Beginn
            - end_date/Enddatum/Bis/To/Ende

    Returns:
        Dict mapping identifier -> [{"start_date": date, "end_date": date}, ...]

    Raises:
        ColumnMappingError: If required columns cannot be found
        ValueError: If data validation fails
    """
    df = load_file_to_dataframe(file_path)

    # Find columns
    col_id = _find_column(
        df, ["identifier", "mitarbeiter", "Mitarbeiter", "staff", "Staff", "kürzel", "Kürzel"]
    )
    col_start = _find_column(
        df, ["start_date", "startdate", "Startdatum", "von", "Von", "from", "From", "beginn", "Beginn"]
    )
    col_end = _find_column(
        df, ["end_date", "enddate", "Enddatum", "bis", "Bis", "to", "To", "ende", "Ende"]
    )

    vacations_dict: dict[str, list[dict[str, Any]]] = {}

    for _, row in df.iterrows():
        identifier = _safe_get_value(row, col_id)
        if not identifier:
            raise ValueError(f"Found vacation row with missing identifier: {row.to_dict()}")

        start_str = _safe_get_value(row, col_start)
        end_str = _safe_get_value(row, col_end)

        if not start_str or not end_str:
            raise ValueError(
                f"Found vacation row for {identifier} with missing date: {row.to_dict()}"
            )

        # Try parsing different date formats
        def parse_date(date_str: str) -> date:
            formats = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"]
            for fmt in formats:
                try:
                    return pd.to_datetime(date_str.strip(), format=fmt).date()
                except (ValueError, TypeError):
                    continue
            # Fallback: try pandas inference
            try:
                return pd.to_datetime(date_str.strip()).date()
            except Exception as e:
                raise ValueError(f"Could not parse date '{date_str}' for {identifier}") from e

        start_date = parse_date(start_str)
        end_date = parse_date(end_str)

        if start_date > end_date:
            raise ValueError(
                f"Invalid date range for {identifier}: {start_date} > {end_date}"
            )

        if identifier not in vacations_dict:
            vacations_dict[identifier] = []

        vacations_dict[identifier].append(
            {
                "identifier": identifier,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    return vacations_dict


# =========================================================================
# PRE-ASSIGNED (HOLIDAY) SHIFT LOADING
# =========================================================================

# Maps column names to Sunday-pattern ShiftTypes
_HOLIDAY_COLUMN_MAP: dict[str, str] = {
    "nachtdienst": "NIGHT",  # Night shift type derived from date
    "dienst_8_20": "So_8-20",
    "dienst_10_22": "So_10-22",
    "azubi_8_2030": "So_8-20:30",
}

_HOLIDAY_COLUMN_ALTERNATIVES: dict[str, list[str]] = {
    "nachtdienst": [
        "nachtdienst", "Nachtdienst", "night", "Night", "ND",
    ],
    "dienst_8_20": [
        "dienst_8_20", "Dienst 8-20", "WE Dienst A", "we_dienst_a",
        "Dienst_8_20", "So_8-20", "dienst8-20",
    ],
    "dienst_10_22": [
        "dienst_10_22", "Dienst 10-22", "WE Dienst B", "we_dienst_b",
        "Dienst_10_22", "So_10-22", "dienst10-22", "rufbereitschaft",
        "Rufbereitschaft",
    ],
    "azubi_8_2030": [
        "azubi_8_2030", "Azubi 8-20:30", "WE Dienst C", "we_dienst_c",
        "Dienst_Azubi", "So_8-20:30", "azubi", "Azubi Dienst",
        "azubi8-2030",
    ],
}

# Night shift type mapping: weekday (0=Mon) -> ShiftType value
_WEEKDAY_TO_NIGHT: dict[int, str] = {
    0: "N_Mo-Di",
    1: "N_Di-Mi",
    2: "N_Mi-Do",
    3: "N_Do-Fr",
    4: "N_Fr-Sa",
    5: "N_Sa-So",
    6: "N_So-Mo",
}


def load_pre_assigned_from_file(
    file_path: Path | str,
) -> list[dict[str, Any]]:
    """Load pre-assigned (holiday) shifts from CSV or XLSX.

    Expected columns:
        - Datum: date of the holiday
        - Nachtdienst: identifier(s) for night shift (e.g. "AA" or "AA + Bax")
        - Dienst 8-20: identifier for So_8-20 shift
        - Dienst 10-22: identifier for So_10-22 shift
        - Azubi 8-20:30: identifier for So_8-20:30 shift

    Returns:
        List of dicts with keys: shift_date, shift_type, staff_identifier, is_paired
    """
    from datetime import date as date_type

    df = load_file_to_dataframe(file_path)

    # Find date column
    col_date = _find_column(
        df, ["datum", "Datum", "date", "Date", "Feiertag", "feiertag"]
    )

    # Find shift columns (all optional except date)
    found_cols: dict[str, str | None] = {}
    for key, alternatives in _HOLIDAY_COLUMN_ALTERNATIVES.items():
        try:
            found_cols[key] = _find_column(df, alternatives)
        except ColumnMappingError:
            found_cols[key] = None

    if not any(found_cols.values()):
        raise ColumnMappingError(
            "No shift columns found. Expected at least one of: "
            "Nachtdienst, Dienst 8-20, Dienst 10-22, Azubi 8-20:30. "
            f"Available columns: {list(df.columns)}"
        )

    def parse_date(date_str: str) -> date_type:
        formats = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"]
        for fmt in formats:
            try:
                return pd.to_datetime(date_str.strip(), format=fmt).date()
            except (ValueError, TypeError):
                continue
        try:
            return pd.to_datetime(date_str.strip()).date()
        except Exception as e:
            raise ValueError(f"Could not parse date '{date_str}'") from e

    results: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        date_val = _safe_get_value(row, col_date)
        if not date_val:
            continue
        shift_date = parse_date(str(date_val))
        weekday = shift_date.weekday()

        for col_key, col_name in found_cols.items():
            if col_name is None:
                continue
            cell = _safe_get_value(row, col_name)
            if not cell:
                continue

            cell = str(cell).strip()
            if not cell:
                continue

            # Determine shift type
            shift_type_map = _HOLIDAY_COLUMN_MAP[col_key]
            if shift_type_map == "NIGHT":
                shift_type_val = _WEEKDAY_TO_NIGHT[weekday]
            else:
                shift_type_val = shift_type_map

            # Parse identifiers (may be "AA + Bax")
            identifiers = [s.strip() for s in cell.split("+") if s.strip()]
            is_paired = len(identifiers) > 1

            for identifier in identifiers:
                results.append({
                    "shift_date": shift_date,
                    "shift_type": shift_type_val,
                    "staff_identifier": identifier,
                    "is_paired": is_paired,
                })

    return results


def parse_previous_plan_xlsx(
    source: "Path | str | IO[bytes]",
) -> list[dict[str, Any]]:
    """Parse a previous quarter's schedule xlsx into a list of assignment dicts.

    Accepts both the legacy single-sheet format and the current two-sheet format
    (sheet 1 = "Nachtdienste", sheet 2 = "Wochenenddienste"). All sheets are
    concatenated before parsing, so either format works transparently.

    Each sheet (or the single sheet) uses the long format:
        Wochentag | Datum        | Mitarbeiter | Schicht | Paarweise
        Mi        | 01.04.2026   | SG          | N_Mi-Do | Ja

    ``Wochentag`` is optional and ignored (derived from date).
    ``Paarweise``: "Ja" (case-insensitive) → is_paired=True, all else → False.
    ``Schicht`` values must match ShiftType enum values exactly (e.g. "N_Mi-Do",
    "Sa_10-22", "So_8-20").

    Args:
        source: File path (Path/str) or file-like object (e.g. Streamlit UploadedFile).

    Returns:
        List of dicts with keys: shift_date (date), shift_type (str),
        staff_identifier (str), is_paired (bool).

    Raises:
        FileFormatError: If required columns are missing.
        ValueError: If a date value cannot be parsed.
    """
    from io import IOBase

    sheets: dict[str, pd.DataFrame] = pd.read_excel(source, sheet_name=None, dtype=str)
    df = pd.concat(sheets.values(), ignore_index=True)

    try:
        col_date = _find_column(df, ["Datum", "datum", "date", "Date"])
        col_shift = _find_column(df, ["Schicht", "schicht", "shift", "Shift", "ShiftType"])
        col_staff = _find_column(df, ["Mitarbeiter", "mitarbeiter", "identifier", "Kürzel"])
        col_paired = _find_column(df, ["Paarweise", "paarweise", "paired", "is_paired"])
    except ColumnMappingError as exc:
        raise FileFormatError(
            f"Previous plan xlsx is missing required columns: {exc}"
        ) from exc

    def _parse_date(raw: str) -> date:
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return pd.to_datetime(raw.strip(), format=fmt).date()
            except (ValueError, TypeError):
                continue
        try:
            return pd.to_datetime(raw.strip()).date()
        except Exception as exc:
            raise ValueError(f"Cannot parse date '{raw}'") from exc

    results: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        raw_date = _safe_get_value(row, col_date)
        raw_shift = _safe_get_value(row, col_shift)
        raw_staff = _safe_get_value(row, col_staff)
        if not raw_date or not raw_shift or not raw_staff:
            continue  # skip blank/header rows

        shift_date = _parse_date(str(raw_date))
        shift_type = str(raw_shift).strip()
        staff_identifier = str(raw_staff).strip()
        raw_paired = _safe_get_value(row, col_paired, default="Nein")
        is_paired = str(raw_paired).strip().lower() == "ja"

        results.append({
            "shift_date": shift_date,
            "shift_type": shift_type,
            "staff_identifier": staff_identifier,
            "is_paired": is_paired,
        })

    return results
