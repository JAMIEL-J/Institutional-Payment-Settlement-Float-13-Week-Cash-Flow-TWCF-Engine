"""Phase 2 tests A: routing edges (6.1 literal, weekends, holidays, EU, rails, contracts)."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402
from src.routing import (  # noqa: E402
    payout_date, inbound_date, build_us_banking_set, PAYOUT_DELTA, RAIL_LAG)


def _bd():
    con = initialize_database()
    bd = build_us_banking_set(con)
    con.close()
    return bd


def test_c1_consecutive_day_no_offbyone():
    bd = _bd()
    tue = date(2026, 1, 6)
    assert payout_date(tue, "NEXT_DAY_T1", bd) == date(2026, 1, 7)


def test_c2_weekend_payout_and_inbound_shift():
    bd = _bd()
    fri = date(2026, 1, 9)
    assert payout_date(fri, "NEXT_DAY_T1", bd) == date(2026, 1, 12)
    # Fri + T+2 -> target Sun Jan 11 -> Mon Jan 12 (calendar-day formula).
    assert inbound_date(fri, "CARD_VISA", bd) == date(2026, 1, 12)
    sat = date(2026, 1, 10)
    assert payout_date(sat, "NEXT_DAY_T1", bd) == date(2026, 1, 12)
    assert inbound_date(sat, "CARD_VISA", bd) == date(2026, 1, 12)


def test_c3_us_holiday_shift_july3():
    bd = _bd()
    thu = date(2026, 7, 2)
    assert payout_date(thu, "NEXT_DAY_T1", bd) == date(2026, 7, 6)
    # Calendar-day formula: Jul 2 + 2 -> Sat Jul 4 (holiday/weekend) -> Mon Jul 6.
    assert inbound_date(thu, "CARD_VISA", bd) == date(2026, 7, 6)
    # Jul 2 + 3 -> Sun Jul 5 -> Mon Jul 6.
    assert inbound_date(thu, "CARD_AMEX", bd) == date(2026, 7, 6)


def test_c4_rail_lag_table():
    bd = _bd()
    tue = date(2026, 1, 6)
    assert RAIL_LAG == {"CARD_VISA": 2, "CARD_MC": 2, "CARD_AMEX": 3,
                        "ACH_STANDARD": 3, "ACH_SAME_DAY": 1, "RTP_FEDNOW": 0}
    assert inbound_date(tue, "RTP_FEDNOW", bd) == date(2026, 1, 6)
    assert inbound_date(tue, "ACH_SAME_DAY", bd) == date(2026, 1, 7)
    assert inbound_date(tue, "CARD_VISA", bd) == date(2026, 1, 8)
    assert inbound_date(tue, "CARD_MC", bd) == date(2026, 1, 8)
    assert inbound_date(tue, "CARD_AMEX", bd) == date(2026, 1, 9)
    assert inbound_date(tue, "ACH_STANDARD", bd) == date(2026, 1, 9)


def test_c5_contract_deltas():
    bd = _bd()
    tue = date(2026, 1, 6)
    assert PAYOUT_DELTA == {"SAME_DAY_RTP": 0, "NEXT_DAY_T1": 1, "TWO_DAY_T2": 2}
    assert payout_date(tue, "SAME_DAY_RTP", bd) == date(2026, 1, 6)
    assert payout_date(tue, "NEXT_DAY_T1", bd) == date(2026, 1, 7)
    assert payout_date(tue, "TWO_DAY_T2", bd) == date(2026, 1, 8)


def test_c6_eu_divergence_calendar_assertion():
    con = initialize_database()
    eu = con.execute("SELECT is_banking_day_eu FROM dim_calendar "
                     "WHERE calendar_date = '2026-04-03'").fetchone()[0]
    us = con.execute("SELECT is_banking_day_us FROM dim_calendar "
                     "WHERE calendar_date = '2026-04-03'").fetchone()[0]
    assert (us, eu) == (True, False)
    con.close()
