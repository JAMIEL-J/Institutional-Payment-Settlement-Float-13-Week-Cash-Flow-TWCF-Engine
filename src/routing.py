"""Clearance scheduling engine: PRD 6.1 literally (fixes I-04/I-05).

P(t) = min{d in C | d >= t + payout_delta(contract)}
S(t,r) = min{d in C | d >= t + rail_delta(r)}
C = US banking-day set for the USD rails in scope. EU/T2 calendar is
maintained (Phase 1) and asserted in tests; EUR-leg routing stays future
work because no PRD rail is EUR-denominated.

Documented assumptions (Phase 0 I-04 carry-forward):
- TWO_DAY_T2 contract delta = 2 (PRD names the contract, gives no delta;
  inside the PRD T+1..T+3 mismatch band).
- ACH_SAME_DAY rail delta = 1 (PRD delta table omits it; same-day ACH still
  clears next banking day when authorized after cutoff/weekend in this model).
- RTP_FEDNOW delta = 0 both legs per PRD 6.1.
"""
from datetime import date, timedelta

from .config import CAL_START, CAL_END

PAYOUT_DELTA = {
    "SAME_DAY_RTP": 0,
    "NEXT_DAY_T1": 1,
    "TWO_DAY_T2": 2,
}

RAIL_LAG = {
    "CARD_VISA": 2,
    "CARD_MC": 2,
    "CARD_AMEX": 3,
    "ACH_STANDARD": 3,
    "ACH_SAME_DAY": 1,
    "RTP_FEDNOW": 0,
}


def build_us_banking_set(con):
    rows = con.execute(
        "SELECT calendar_date FROM dim_calendar "
        "WHERE is_banking_day_us ORDER BY calendar_date").fetchall()
    return sorted(r[0] if isinstance(r[0], date) else r[0].date() for r in rows)


def _settle(auth_date, delta, banking_days):
    target = auth_date + timedelta(days=delta)
    for d in banking_days:
        if d >= target:
            return d
    return banking_days[-1]


def payout_date(auth_date, contract, banking_days):
    return _settle(auth_date, PAYOUT_DELTA[contract], banking_days)


def inbound_date(auth_date, rail, banking_days):
    return _settle(auth_date, RAIL_LAG[rail], banking_days)


def calendar_span(num_days, start=CAL_START):
    return [start + timedelta(days=i) for i in range(num_days)]
