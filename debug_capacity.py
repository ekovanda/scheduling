"""Analyze night staffing capacity -- solo vs paired workers."""

import pandas as pd

df = pd.read_excel("data/MA_excel.xlsx", dtype=str)

nd_staff = df[df["nd_possible"].str.lower().isin(["true", "ja", "yes", "1"])]


def is_true(val):
    if pd.isna(val):
        return False
    return str(val).strip().lower() in ["true", "ja", "yes", "1"]


def count_exc(exc_str):
    if pd.isna(exc_str) or exc_str.strip() in ("[]", ""):
        return 0
    return len([x for x in exc_str.strip("[]").split(",") if x.strip()])


print(f"Total staff: {len(df)}")
print(f"Night-eligible: {len(nd_staff)}")

alone_true = nd_staff[nd_staff["nd_alone"].apply(is_true)]
alone_false = nd_staff[~nd_staff["nd_alone"].apply(is_true)]

print(f"\nnd_alone=True (MUST work solo, forces total=1 on that night):")
for _, r in alone_true.iterrows():
    exc = r.get("nd_exceptions", "[]")
    avail = 7 - count_exc(exc)
    print(f"  {r['name']:20s} ({r['identifier']:5s}) beruf={r['beruf']:6s} avail_types={avail}")

print(f"\nnd_alone=False (must pair with someone, forces total=2):")
for _, r in alone_false.iterrows():
    exc = r.get("nd_exceptions", "[]")
    avail = 7 - count_exc(exc)
    print(f"  {r['name']:20s} ({r['identifier']:5s}) beruf={r['beruf']:6s} avail_types={avail}")

# Key constraint: nd_alone=True person works -> nobody else can work that night
# nd_alone=False person works -> must have exactly 1 other person (paired)
# Azubi can only work paired with a non-Azubi

# Count how many nights per week: 7 nights/week
# Each needs at least 1 non-Azubi
# Solo workers: if assigned, only they work
# Paired workers: exactly 2 people, at least 1 non-Azubi

print("\n\nNight coverage analysis:")
print("91 nights in Q2, each needs >= 1 non-Azubi")
non_azubi_nd = nd_staff[nd_staff["beruf"] != "Azubi"]
azubi_nd = nd_staff[nd_staff["beruf"] == "Azubi"]
print(f"Non-Azubi night-eligible: {len(non_azubi_nd)}")
print(f"Azubi night-eligible: {len(azubi_nd)}")
