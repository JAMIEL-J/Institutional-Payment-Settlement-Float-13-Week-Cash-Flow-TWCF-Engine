"""US + EU banking-day calendar builder (PRD 5.1, Phase 0 FN-01/FN-02).

next_banking_day_us semantics (documented assumption): INCLUSIVE — a US
banking day resolves to itself; a non-banking day resolves forward to the
next US banking day. This matches the PRD dictionary wording ("resolving
non-banking days to the next clearing date"). The reference code used a
strictly-future lookup instead; Phase 2 routing follows the PRD 6.1
formula (d >= t + delta) and does not depend on this column for math.
"""
from datetime import timedelta
import pandas as pd

from .config import (
    CAL_START, CAL_END,
    FED_HOLIDAYS_2026_OBSERVED, T2_EURO_CLOSURES_2026,
)


def is_us_banking_day(d):
    return d.weekday() < 5 and d not in FED_HOLIDAYS_2026_OBSERVED


def is_eu_banking_day(d):
    return d.weekday() < 5 and d not in T2_EURO_CLOSURES_2026


def build_calendar_df(start=CAL_START, end=CAL_END):
    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    records = [
        {
            "calendar_date": d,
            "day_of_week": d.strftime("%A"),
            "is_weekend": d.weekday() >= 5,
            "is_banking_day_us": is_us_banking_day(d),
            "is_banking_day_eu": is_eu_banking_day(d),
        }
        for d in days
    ]
    df = pd.DataFrame(records)
    # Inclusive forward fill of next US banking day.
    nxt = None
    next_vals = [None] * len(df)
    for i in range(len(df) - 1, -1, -1):
        if df.loc[i, "is_banking_day_us"]:
            nxt = df.loc[i, "calendar_date"]
        next_vals[i] = nxt if nxt is not None else df.loc[i, "calendar_date"]
    df["next_banking_day_us"] = next_vals
    return df
