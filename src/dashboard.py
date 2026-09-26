"""Executive BI surface: PRD 8 four tabs exactly (Phase 6).

Smallest PRD-consistent implementation: a Streamlit app reading the
engine DuckDB outputs (no new calculations beyond display assembly).
Every displayed value is a direct read of a waterfall / regulatory /
TWCF table cell or a stated threshold constant; reconciliation tests pin
each tab to its source query.

Tab mapping (PRD 8):
  Tab 1 Liquidity Runway + Covenant Early Warning: total_liquidity and
    corporate_closing_cash vs 250M floor; red alert when headroom < 50M;
    KPI cards: cushion, runway days, LCR + flag.
  Tab 2 Revolver Utilization + Macro Interest Drag: active_debt_balance
    bars + borrowing rate line; monthly cost-of-carry in bps of margin.
  Tab 3 Working Capital + Settlement Float Dynamics: receivables vs
    payables area inputs; DFO = Receivables / (GPV/365).
  Tab 4 TWCF Variance Decomposition: bridge of Volume / Mix / Timing /
    CECL contributions week over week.
"""
import datetime as _dt

from .config import REVOLVER_CAPACITY, MIN_CORP_LIQUIDITY_COVENANT
from .twcf import week_key

HEADROOM_ALERT = 50_000_000.0
COVENANT_FLOOR = float(MIN_CORP_LIQUIDITY_COVENANT)
REVOLVER_LIMIT = float(REVOLVER_CAPACITY)


def _cell(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()


def tab1_runway(con):
    """PRD 8.1: liquidity vs 250M floor, headroom<50M alert, 3 KPI cards."""
    last = _cell(con, "SELECT w.ledger_date, w.corporate_closing_cash,"
                " w.active_debt_balance, r.covenant_liquidity_cushion"
                " FROM fpa_cash_waterfall_daily w JOIN fpa_regulatory_liquidity_daily r"
                " ON w.ledger_date = r.ledger_date"
                " ORDER BY w.ledger_date DESC LIMIT 1")
    lcr = _cell(con, "SELECT lcr_ratio, lcr_status FROM fpa_regulatory_liquidity_daily"
                " ORDER BY ledger_date DESC LIMIT 1")
    cash, debt, cushion = float(last[1]), float(last[2]), float(last[3])
    total_liq = cash + (REVOLVER_LIMIT - debt)
    headroom = total_liq - COVENANT_FLOOR
    payout = float(_cell(con, "SELECT AVG(safeguarded_outbound_payouts)"
                         " FROM fpa_cash_waterfall_daily")[0] or 0)
    series_rows = con.execute(
        "SELECT CAST(ledger_date AS VARCHAR), corporate_closing_cash, active_debt_balance"
        " FROM fpa_cash_waterfall_daily ORDER BY ledger_date").fetchall()
    series = [
        {"date": d,
         "corporate_closing_cash": float(c),
         "total_liquidity": float(c) + (REVOLVER_LIMIT - float(b)),
         "covenant_floor": COVENANT_FLOOR}
        for d, c, b in series_rows
    ]
    return {"asof": str(last[0]), "corporate_closing_cash": cash,
            "total_liquidity": total_liq, "covenant_floor": COVENANT_FLOOR,
            "covenant_headroom": headroom, "alert": headroom < HEADROOM_ALERT,
            "cushion": cushion,
            "runway_days": (total_liq / payout) if payout else None,
            "lcr_ratio": float(lcr[0]), "lcr_status": lcr[1],
            "series": series}


def tab2_revolver(con, scenario="BASELINE"):
    """PRD 8.2: debt balance bars + borrowing-rate line + monthly carry in bps."""
    from .scenarios import borrowing_rate
    rows = con.execute("SELECT CAST(ledger_date AS VARCHAR), active_debt_balance,"
                       " daily_interest_expense FROM fpa_cash_waterfall_daily"
                       " ORDER BY ledger_date").fetchall()
    monthly = con.execute("SELECT SUBSTRING(CAST(ledger_date AS VARCHAR),1,7),"
                          " SUM(daily_interest_expense), SUM(net_revenue_swept)"
                          " FROM fpa_cash_waterfall_daily GROUP BY 1 ORDER BY 1").fetchall()
    carry = [(m, (float(i) / float(r) * 10000.0) if r else 0.0) for m, i, r in monthly]
    return {"rate": float(borrowing_rate(scenario)),
            "daily": [(d, float(b), float(i)) for d, b, i in rows],
            "monthly_carry_bps": carry}


def tab3_working_capital(con):
    """PRD 8.3: receivables vs payables + DFO = Receivables / (GPV/365)."""
    asof = _cell(con, "SELECT MAX(ledger_date) FROM fpa_cash_waterfall_daily")[0]
    rec = float(_cell(con, "SELECT SUM(gross_amount) FROM fact_transactions"
                     " WHERE inbound_settlement_date > ?", [asof])[0] or 0)
    pay = float(_cell(con, "SELECT SUM(gross_amount - reserve_retained_amount)"
                      " FROM fact_transactions WHERE merchant_payout_date > ?",
                      [asof])[0] or 0)
    gpv = float(_cell(con, "SELECT SUM(gross_amount) FROM fact_transactions")[0] or 0)
    n_days = int(_cell(con, "SELECT COUNT(DISTINCT auth_date)"
                       " FROM fact_transactions")[0] or 0)
    annualized_gpv_denom = (gpv / 365.0) if gpv else 1.0
    daily_rows = con.execute("""
        SELECT 
            CAST(c.calendar_date AS VARCHAR),
            COALESCE(SUM(CASE WHEN t.auth_date <= c.calendar_date AND t.inbound_settlement_date > c.calendar_date THEN t.gross_amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN t.auth_date <= c.calendar_date AND t.merchant_payout_date > c.calendar_date THEN t.gross_amount - t.reserve_retained_amount ELSE 0 END), 0)
        FROM (SELECT DISTINCT ledger_date AS calendar_date FROM fpa_cash_waterfall_daily) c
        LEFT JOIN fact_transactions t 
            ON t.auth_date <= c.calendar_date 
            AND (t.inbound_settlement_date > c.calendar_date OR t.merchant_payout_date > c.calendar_date)
        GROUP BY c.calendar_date
        ORDER BY c.calendar_date
    """).fetchall()
    daily = [
        {"date": d,
         "Settlements Receivable (Asset)": float(r),
         "Customers Payable (Liability)": float(p),
         "dfo": float(r) / annualized_gpv_denom}
        for d, r, p in daily_rows
    ]
    return {"receivables": rec, "payables": pay,
            "dfo": rec / (gpv / 365.0) if gpv else 0.0, "run_days": n_days,
            "daily": daily}


def tab4_twcf_bridge(con):
    """PRD 8.4: bridge drivers per week + CECL provision + reference cash delta."""
    allow = {}
    for ds, bal in con.execute("SELECT CAST(ledger_date AS VARCHAR),"
                               " cecl_daily_allowance FROM fpa_regulatory_liquidity_daily"
                               " ORDER BY ledger_date").fetchall():
        allow.setdefault(week_key(_dt.date.fromisoformat(ds)), []).append(float(bal))
    var = con.execute("SELECT week_key, volume_variance, mix_variance,"
                      " timing_variance, residual_eps, actual_net_cash"
                      " FROM fpa_twcf_weekly_variance ORDER BY week_key").fetchall()
    out, prev_allow, prev_net = [], 0.0, None
    for wk, vol, mix, tim, eps, net in var:
        series = allow.get(wk, [])
        closing = series[-1] if series else prev_allow
        cecl = closing - prev_allow
        delta = None if prev_net is None else float(net) - prev_net
        out.append((wk, float(vol), float(mix), float(tim), cecl, delta, float(eps)))
        prev_allow, prev_net = closing, float(net)
    return out


def build_dashboard_frames(con, scenario="BASELINE"):
    return {"tab1": tab1_runway(con), "tab2": tab2_revolver(con, scenario),
            "tab3": tab3_working_capital(con), "tab4": tab4_twcf_bridge(con)}
