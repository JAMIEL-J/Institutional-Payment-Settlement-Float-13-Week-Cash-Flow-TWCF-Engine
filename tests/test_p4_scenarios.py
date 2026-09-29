"""Phase 4 tests: scenarios, Actual/360, CECL, LCR bands, covenants, stress."""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402
from src.transactions import seed_merchants, generate_synthetic_transactions  # noqa: E402
from src.waterfall import execute_daily_waterfall_engine, daily_flows  # noqa: E402
from src.scenarios import (  # noqa: E402
    borrowing_rate, daily_interest_expense, cecl_daily_charge, lcr_for_day,
    covenant_breach, leverage_ratio, leverage_breach, net_cecl_exposure,
    LAG_SHIFT_DAYS)


def _big_con(days=150):
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, num_days=days)
    return con


def test_f1_scenario_params_and_interest():
    assert borrowing_rate("BASELINE") == Decimal("0.0425") + Decimal("0.0200")
    assert borrowing_rate("ADVERSE") == Decimal("0.0575") + Decimal("0.0275")
    assert borrowing_rate("SEVERELY_ADVERSE") == Decimal("0.0700") + Decimal("0.0375")
    assert daily_interest_expense(500000000, "BASELINE") == Decimal("86805.56")
    assert daily_interest_expense(500000000, "ADVERSE") == Decimal("118055.56")
    assert daily_interest_expense(500000000, "SEVERELY_ADVERSE") == Decimal("149305.56")
    assert LAG_SHIFT_DAYS == {"BASELINE": 0, "ADVERSE": 1, "SEVERELY_ADVERSE": 2}


def test_f2_cecl_gpv_proxy_and_allowance():
    assert cecl_daily_charge(600000000, "BASELINE") == Decimal("600000.00")
    assert cecl_daily_charge(600000000, "ADVERSE") == Decimal("4620000.00")
    assert cecl_daily_charge(600000000, "SEVERELY_ADVERSE") == Decimal("17850000.00")
    con = _big_con(30)
    execute_daily_waterfall_engine(con, macro_scenario="ADVERSE",
                                   end=date(2026, 1, 30))
    rows = con.execute("SELECT cecl_daily_allowance FROM fpa_regulatory_liquidity_daily"
                       " ORDER BY ledger_date").fetchall()
    assert float(rows[-1][0]) > 0
    assert float(rows[-1][0]) >= float(rows[5][0]) >= 0
    assert float(rows[5][0]) > 0
    gpv = con.execute("SELECT SUM(gross_amount) FROM fact_transactions"
                      " WHERE merchant_payout_date BETWEEN '2026-01-01' AND '2026-01-30'"
                      ).fetchone()[0]
    expect = float(gpv) * 0.011 * 0.70
    assert abs(float(rows[-1][0]) - expect) / expect < 0.02
    assert net_cecl_exposure(Decimal("100"), Decimal("30")) == Decimal("70")
    assert net_cecl_exposure(Decimal("10"), Decimal("30")) == Decimal("0.00")
    con.close()


def test_f3_lcr_thirtieth_and_bands():
    ratio, out, status = lcr_for_day(300000000, 600000000)
    assert out == Decimal("5400000000.00")
    assert status == "BREACH"
    _, _, s2 = lcr_for_day(5500000000, 600000000)
    assert s2 == "WARNING"
    _, _, s3 = lcr_for_day(6000000000, 600000000)
    assert s3 == "COMPLIANT"
    con = _big_con(40)
    execute_daily_waterfall_engine(con, end=date(2026, 2, 9))
    rows = con.execute("SELECT total_hqla_level1, stressed_30d_net_outflows, lcr_ratio,"
                       " lcr_status FROM fpa_regulatory_liquidity_daily"
                       " ORDER BY ledger_date").fetchall()
    for hqla, denom, ratio, status in rows[30:]:
        if float(denom) <= 0:
            assert status == "COMPLIANT"
            continue
        assert abs(float(ratio) - float(hqla) / float(denom)) / (float(hqla) / float(denom)) < 0.01
        if float(ratio) >= 1.05:
            assert status == "COMPLIANT"
        elif float(ratio) >= 1.00:
            assert status == "WARNING"
        else:
            assert status == "BREACH"
    con.close()


def test_f4_covenant_leverage_capacity_stress():
    assert covenant_breach(300000000, 0) is False
    assert covenant_breach(100000000, 500000000) is True
    assert leverage_ratio(400000000, 300000000, Decimal("100000000")) == Decimal("1.0000")
    assert leverage_breach(400000000, 300000000, Decimal("100000000")) is False
    assert leverage_breach(400000000, 0, Decimal("100000000")) is True
    assert leverage_ratio(100, 50, None) is None
    assert leverage_breach(100, 50, None) is None
    con = _big_con(150)
    df = execute_daily_waterfall_engine(con, macro_scenario="SEVERELY_ADVERSE")
    assert (df["active_debt_balance"].astype(float) <= 500000000.0 + 0.01).all()
    assert (df["active_debt_balance"].astype(float) >= -0.01).all()
    base0 = daily_flows(con, date(2026, 1, 6), date(2026, 1, 6), lag_shift_days=0)[0][1]
    sev0 = daily_flows(con, date(2026, 1, 6), date(2026, 1, 6), lag_shift_days=2)[0][1]
    assert float(sev0) <= float(base0) + 0.01
    con.close()
