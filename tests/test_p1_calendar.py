"""Phase 1 focused tests A: calendar keys, types, banking-day behavior."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402


def test_a1_row_count_and_bounds():
    con = initialize_database()
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT calendar_date) FROM dim_calendar").fetchone()
    assert (n[0], n[1]) == (365, 365)
    lo, hi = con.execute("SELECT MIN(calendar_date), MAX(calendar_date) FROM dim_calendar").fetchone()
    assert str(lo) == "2026-01-01" and str(hi) == "2026-12-31"
    con.close()


def test_a2_column_types():
    con = initialize_database()
    types = {r[0]: r[1] for r in con.execute("DESCRIBE dim_calendar").fetchall()}
    assert types["calendar_date"] == "DATE"
    assert types["is_banking_day_us"] == "BOOLEAN"
    assert types["is_banking_day_eu"] == "BOOLEAN"
    assert types["next_banking_day_us"] == "DATE"
    con.close()


def test_a3_us_holidays_2026():
    con = initialize_database()
    cases = [("2026-01-01", False), ("2026-01-19", False), ("2026-02-16", False),
             ("2026-05-25", False), ("2026-06-19", False), ("2026-07-03", False),
             ("2026-07-04", False), ("2026-09-07", False), ("2026-10-12", False),
             ("2026-11-11", False), ("2026-11-26", False), ("2026-12-25", False),
             ("2026-01-02", True), ("2026-07-02", True), ("2026-07-06", True)]
    for d, exp in cases:
        got = con.execute(
            "SELECT is_banking_day_us FROM dim_calendar WHERE calendar_date = '" + d + "'").fetchone()[0]
        assert got is exp, d
    con.close()


def test_a4_eu_target2_distinction():
    con = initialize_database()
    q = ("SELECT CAST(calendar_date AS VARCHAR), is_banking_day_us, is_banking_day_eu "
         "FROM dim_calendar WHERE calendar_date IN "
         "(DATE '2026-04-03', DATE '2026-04-06', DATE '2026-05-01')")
    rows = {r[0]: (r[1], r[2]) for r in con.execute(q).fetchall()}
    assert rows["2026-04-03"] == (True, False)
    assert rows["2026-04-06"] == (True, False)
    # 1 May is NOT a US Federal holiday: US open, EU/T2 closed.
    assert rows["2026-05-01"] == (True, False)
    assert con.execute("SELECT COUNT(*) FROM dim_calendar WHERE is_weekend AND "
                       "(is_banking_day_us OR is_banking_day_eu)").fetchone()[0] == 0
    con.close()


def test_a5_next_banking_day_lookup():
    con = initialize_database()
    assert str(con.execute("SELECT next_banking_day_us FROM dim_calendar WHERE "
                           "calendar_date = DATE '2026-07-03'").fetchone()[0]) == "2026-07-06"
    assert str(con.execute("SELECT next_banking_day_us FROM dim_calendar WHERE "
                           "calendar_date = DATE '2026-07-04'").fetchone()[0]) == "2026-07-06"
    assert str(con.execute("SELECT next_banking_day_us FROM dim_calendar WHERE "
                           "calendar_date = DATE '2026-07-02'").fetchone()[0]) == "2026-07-02"
    assert con.execute("SELECT COUNT(*) FROM dim_calendar c JOIN dim_calendar n ON "
                       "n.calendar_date = c.next_banking_day_us "
                       "WHERE n.is_banking_day_us = FALSE").fetchone()[0] == 0
    con.close()
