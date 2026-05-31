"""Check pre-assigned shift counts per holiday date."""

import pandas as pd

df = pd.read_excel("data/Feiertage_Excel.xlsx", dtype=str)

for _, r in df.iterrows():
    datum = str(r["Datum"])[:10]
    print(f"\n{datum}:")
    for col in ["ND", "dienst_8_20", "dienst_10_22", "azubi_8_2030"]:
        val = r.get(col, "")
        if pd.isna(val) or not str(val).strip():
            continue
        val = str(val).strip()
        people = [x.strip() for x in val.split("+") if x.strip()]
        shift_map = {
            "ND": "Night",
            "dienst_8_20": "So_8-20",
            "dienst_10_22": "So_10-22",
            "azubi_8_2030": "So_8-20:30",
        }
        shift_name = shift_map.get(col, col)
        flag = " *** PAIRED on day shift! ***" if len(people) > 1 and col != "ND" else ""
        print(f"  {shift_name:15s} = {val:20s} -> {len(people)} person(s){flag}")
