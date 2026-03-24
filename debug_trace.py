"""Trace available night dates for the 3 failing staff in Q2."""

from datetime import date, timedelta


def daterange(s: date, e: date):
    d = s
    while d <= e:
        yield d
        d += timedelta(days=1)


q_start = date(2026, 4, 1)
q_end = date(2026, 6, 30)

staff = {
    "Jul": {"exc": [1, 2, 3, 4, 7], "min_c": 1, "alone": True, "beruf": "TFA"},
    "HD": {"exc": [1, 2, 3, 4, 7], "min_c": 1, "alone": False, "beruf": "Azubi"},
    "DK": {"exc": [1, 2, 3, 4, 7], "min_c": 1, "alone": True, "beruf": "TFA"},
}

vacations = {
    "Jul": (
        list(daterange(date(2026, 4, 4), date(2026, 4, 5)))
        + list(daterange(date(2026, 4, 7), date(2026, 4, 12)))
        + [date(2026, 5, 8), date(2026, 5, 15)]
        + list(daterange(date(2026, 6, 26), date(2026, 6, 30)))
    ),
    "HD": (
        list(daterange(date(2026, 4, 7), date(2026, 4, 12)))
        + list(daterange(date(2026, 4, 27), date(2026, 5, 1)))
    ),
    "DK": (
        list(daterange(date(2026, 3, 30), date(2026, 4, 2)))
        + list(daterange(date(2026, 4, 4), date(2026, 4, 5)))
    ),
}

# Pre-assigned holidays (from Feiertage_Excel.xlsx)
pre_assigned = {
    "Jul": [date(2026, 5, 25)],  # dienst_8_20, May 25 is Monday
    "HD": [date(2026, 6, 4)],  # azubi_8_2030, Jun 4 is Thursday
    "DK": [],
}

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

for sid, info in staff.items():
    avail_iso = [d for d in range(1, 8) if d not in info["exc"]]
    beruf = info["beruf"]
    alone = info["alone"]
    print(f"\n=== {sid} (beruf={beruf}, alone={alone}) ===")
    print(f"Available night isoweekdays: {avail_iso} = {[WEEKDAY_NAMES[i-1] for i in avail_iso]}")

    vac_set = set(vacations.get(sid, []))
    pa_dates = set(pre_assigned.get(sid, []))

    available_nights = []
    d = q_start
    while d <= q_end:
        iso = d.isoweekday()
        if iso in avail_iso and d not in vac_set:
            available_nights.append(d)
        d += timedelta(days=1)

    print(f"Pre-assigned dates: {pa_dates}")
    print(f"Available night dates: {len(available_nights)}")
    for nd in available_nights:
        wday = WEEKDAY_NAMES[nd.weekday()]
        marker = " <-- PRE-ASSIGNED DAY" if nd in pa_dates else ""
        print(f"  {nd} ({wday}){marker}")

    # Now check: which of these can form valid block starts
    # considering 3-week (or 1-week for pre-assigned) gaps?
    print(f"\nBlock gap analysis (gap=21d, holiday gap=7d):")
    print(f"  NOTE: Pre-assigned day shift (not night) creates a block.")
    print(f"  If Jul works dienst_8_20 on May 25, that's a block start.")
    print(f"  Then a night shift must start >= 7d away (Jun 1 or later).")
    for pa_d in pa_dates:
        wday = WEEKDAY_NAMES[pa_d.weekday()]
        print(f"  Pre-assigned block on {pa_d} ({wday})")
        print(f"    7-day exclusion zone: {pa_d + timedelta(days=1)} to {pa_d + timedelta(days=6)}")
        print(f"    21-day exclusion zone: {pa_d + timedelta(days=1)} to {pa_d + timedelta(days=20)}")
        # Which night dates fall outside exclusion?
        ok_7d = [nd for nd in available_nights if abs((nd - pa_d).days) >= 7 or nd == pa_d]
        ok_21d = [nd for nd in available_nights if abs((nd - pa_d).days) >= 21 or nd == pa_d]
        print(f"    Nights available with 7d gap: {len(ok_7d)}")
        print(f"    Nights available with 21d gap: {len(ok_21d)}")
