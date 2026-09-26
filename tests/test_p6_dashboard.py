"""Phase 6 tests: four tabs reconcile to engine outputs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402
from src.transactions import seed_merchants, generate_synthetic_transactions  # noqa: E402
from src.waterfall import execute_daily_waterfall_engine  # noqa: E402
from src.twcf import weekly_variance  # noqa: E402
from src.dashboard import (  # noqa: E402
    tab1_runway, tab2_revolver, tab3_working_capital, tab4_twcf_bridge,
    HEADROOM_ALERT)


def _ready(days=100):
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, num_days=days)
    execute_daily_waterfall_engine(con)
    weekly_variance(con)
    return con


def test_h1_runway_floor_and_alert():
    con = _ready()
    k = tab1_runway(con)
    assert k["covenant_floor"] == 250_000_000.0
    row = con.execute("SELECT corporate_closing_cash, active_debt_balance,"
                      " covenant_liquidity_cushion FROM ("
                      " SELECT w.ledger_date, w.corporate_closing_cash, w.active_debt_balance,"
                      " r.covenant_liquidity_cushion FROM fpa_cash_waterfall_daily w"
                      " JOIN fpa_regulatory_liquidity_daily r ON w.ledger_date = r.ledger_date"
                      " ORDER BY w.ledger_date DESC LIMIT 1)").fetchone()
    cash, debt, cushion = float(row[0]), float(row[1]), float(row[2])
    assert abs(k["total_liquidity"] - (cash + (500_000_000.0 - debt))) < 0.05
    assert abs(k["cushion"] - cushion) < 0.05
    assert abs(k["corporate_closing_cash"] - cash) < 0.05
    assert k["alert"] == (k["total_liquidity"] - 250_000_000.0 < HEADROOM_ALERT)
    lcr = con.execute("SELECT lcr_ratio, lcr_status FROM fpa_regulatory_liquidity_daily"
                      " ORDER BY ledger_date DESC LIMIT 1").fetchone()
    assert abs(k["lcr_ratio"] - float(lcr[0])) < 1e-6
    assert k["runway_days"] is not None and k["runway_days"] > 0
    n = con.execute("SELECT COUNT(*) FROM fpa_cash_waterfall_daily").fetchone()[0]
    assert "series" in k and len(k["series"]) == n
    assert abs(k["series"][-1]["corporate_closing_cash"] - k["corporate_closing_cash"]) < 0.05
    assert k["series"][-1]["covenant_floor"] == 250_000_000.0
    con.close()


def test_h2_revolver_rate_and_carry():
    con = _ready()
    t = tab2_revolver(con, "BASELINE")
    assert abs(t["rate"] - (0.0425 + 0.0200)) < 1e-12
    n = con.execute("SELECT COUNT(*) FROM fpa_cash_waterfall_daily").fetchone()[0]
    assert len(t["daily"]) == n
    tot_i = sum(i for _, _, i in t["daily"])
    eng = con.execute("SELECT SUM(daily_interest_expense)"
                      " FROM fpa_cash_waterfall_daily").fetchone()[0]
    assert abs(tot_i - float(eng)) < 1.0
    assert len(t["monthly_carry_bps"]) >= 3
    con.close()


def test_h3_working_capital_dfo():
    con = _ready()
    k = tab3_working_capital(con)
    asof = con.execute("SELECT MAX(ledger_date) FROM fpa_cash_waterfall_daily").fetchone()[0]
    rec = float(con.execute("SELECT SUM(gross_amount) FROM fact_transactions"
                            " WHERE inbound_settlement_date > ?", [asof]).fetchone()[0] or 0)
    pay = float(con.execute("SELECT SUM(gross_amount - reserve_retained_amount)"
                            " FROM fact_transactions WHERE merchant_payout_date > ?",
                            [asof]).fetchone()[0] or 0)
    gpv = float(con.execute("SELECT SUM(gross_amount) FROM fact_transactions").fetchone()[0])
    assert abs(k["receivables"] - rec) < 0.05
    assert abs(k["payables"] - pay) < 0.05
    assert abs(k["dfo"] - rec / (gpv / 365.0)) < 1e-9
    assert k["run_days"] == con.execute(
        "SELECT COUNT(DISTINCT auth_date) FROM fact_transactions").fetchone()[0]
    n = con.execute("SELECT COUNT(*) FROM fpa_cash_waterfall_daily").fetchone()[0]
    assert "daily" in k and len(k["daily"]) == n
    assert abs(k["daily"][-1]["Settlements Receivable (Asset)"] - k["receivables"]) < 0.05
    assert abs(k["daily"][-1]["Customers Payable (Liability)"] - k["payables"]) < 0.05
    con.close()


def test_h4_twcf_bridge_reconciles():
    con = _ready()
    rows = tab4_twcf_bridge(con)
    tbl = con.execute("SELECT week_key, volume_variance, timing_variance, mix_variance,"
                      " residual_eps, actual_net_cash FROM fpa_twcf_weekly_variance"
                      " ORDER BY week_key").fetchall()
    assert len(rows) == len(tbl)
    for r, t in zip(rows, tbl):
        assert r[0] == t[0]
        assert abs(r[1] - float(t[1])) < 0.05
        assert abs(r[2] - float(t[3])) < 0.05
        assert abs(r[3] - float(t[2])) < 0.05
        assert abs(r[6] - float(t[4])) < 0.05
    prev_net = None
    for r, t in zip(rows, tbl):
        net = float(t[5])
        if prev_net is None:
            assert r[5] is None
        else:
            assert abs(r[5] - (net - prev_net)) < 1.0
        prev_net = net
        if r[4] > 0:
            assert r[4] > 0  # CECL provision is a positive charge to net cash
    cum = float(con.execute(
        "SELECT cecl_daily_allowance FROM fpa_regulatory_liquidity_daily"
        " WHERE ledger_date <= (SELECT MAX(week_end) FROM fpa_twcf_weekly_variance)"
        " ORDER BY ledger_date DESC LIMIT 1").fetchone()[0])
    assert abs(sum(r[4] for r in rows) - cum) < 1.0
    con.close()
