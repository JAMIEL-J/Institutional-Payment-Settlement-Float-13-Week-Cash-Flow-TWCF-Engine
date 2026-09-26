"""Rolling 13-week forecast + Volume/Timing/Mix variance (Phase 5).

Week convention frozen here (closes I-10): ISO calendar weeks
(Monday-Sunday), week_key = YYYY-Www of the ledger date. Budget/forecast
join keys: (week_key, scenario). Epsilon tolerance: residual |eps| must be
<= 1% of |dNCF| on weeks with non-trivial actuals; decomposition is
additive by construction so eps is rounding only.

Formulas (PRD 6.3):
  Volume_k = (ActualGPV_k - BudgetGPV_k) * budget_net_take
  Timing_k = sum_d (ActualInbound_d - ForecastInbound_d) at constant GPV
  Mix_k    = ActualGPV_k * sum_r (w_act - w_bud) * (take_r - cost_r)
  dNCF_k   = Volume + Timing + Mix + eps, reconciling to
             ActualNetCash_k - BudgetNetCash_k.

Forecast surface: forecast_13w(asof, scenario) returns the next 13 ISO
weeks of expected inbound/outbound/net from the daily waterfall ledger
(Actual/360 financing excluded; pure settlement cash). Variance surface:
weekly_variance(con, budget_gpv, budget_mix, budget_take, forecast_inbound)
writes fpa_twcf_weekly_variance.
"""
import datetime as _dt
from decimal import Decimal as _D, ROUND_HALF_UP as _H

from .config import BASELINE_DAILY_GPV
from .transactions import RAIL_SHARE, RAIL_TAKE, RAIL_COST

DDL_TWCF = """
CREATE TABLE IF NOT EXISTS fpa_twcf_weekly_variance (
    week_key VARCHAR PRIMARY KEY,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    actual_gpv DECIMAL(16,2) NOT NULL,
    budget_gpv DECIMAL(16,2) NOT NULL,
    actual_net_cash DECIMAL(16,2) NOT NULL,
    budget_net_cash DECIMAL(16,2) NOT NULL,
    volume_variance DECIMAL(16,2) NOT NULL,
    timing_variance DECIMAL(16,2) NOT NULL,
    mix_variance DECIMAL(16,2) NOT NULL,
    residual_eps DECIMAL(16,2) NOT NULL
);
"""

EPS_TOL = _D("0.01")


def ensure_twcf_table(con):
    con.execute(DDL_TWCF)


def iso_week_bounds(d):
    start = d - _dt.timedelta(days=d.weekday())
    return start, start + _dt.timedelta(days=6)


def week_key(d):
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"



def forecast_13w(con, asof):
    rows = con.execute(
        "SELECT ledger_date, safeguarded_inbound_settlements,"
        " safeguarded_outbound_payouts FROM fpa_cash_waterfall_daily"
        " WHERE ledger_date > ? ORDER BY ledger_date LIMIT 91", [asof]).fetchall()
    out = []
    for i in range(0, 91, 7):
        chunk = rows[i:i + 7]
        if not chunk:
            break
        start = chunk[0][0]
        if hasattr(start, "date"):
            start = start.date()
        end = chunk[-1][0]
        if hasattr(end, "date"):
            end = end.date()
        inbound = sum(float(r[1]) for r in chunk)
        payout = sum(float(r[2]) for r in chunk)
        out.append({"week_start": start, "week_end": end,
                    "forecast_inbound": inbound, "forecast_payout": payout,
                    "forecast_net": inbound - payout})
    return out


def weekly_variance(con, budget_daily_gpv=None, budget_mix=None,
                    budget_take=None, forecast_inbound=None):
    import pandas as _pd
    ensure_twcf_table(con)
    if budget_daily_gpv is None:
        budget_daily_gpv = BASELINE_DAILY_GPV
    if budget_mix is None:
        budget_mix = dict(RAIL_SHARE)
    if budget_take is None:
        budget_take = {r: RAIL_TAKE[r] - RAIL_COST[r] for r in RAIL_SHARE}
    budget_net_take = sum(budget_mix[r] * budget_take[r] for r in budget_mix)
    inbound_by_day = {}
    for ds, v in con.execute("SELECT CAST(inbound_settlement_date AS VARCHAR),"
                             " SUM(gross_amount) FROM fact_transactions"
                             " GROUP BY 1").fetchall():
        inbound_by_day[str(ds)] = float(v or 0)
    days = [str(r[0]) for r in con.execute(
        "SELECT DISTINCT CAST(auth_date AS VARCHAR) FROM fact_transactions"
        " ORDER BY 1").fetchall()]
    weeks = {}
    for ds in days:
        d = _dt.date.fromisoformat(ds)
        weeks.setdefault(week_key(d), []).append(d)
    if forecast_inbound is None:
        forecast_inbound = {wk: sum(inbound_by_day.get(x.isoformat(), 0.0)
                                    for x in ds) for wk, ds in weeks.items()}
    out_rows = []
    for wk in sorted(weeks):
        ds = weeks[wk]
        act_gpv = float(con.execute(
            "SELECT COALESCE(SUM(gross_amount),0) FROM fact_transactions"
            " WHERE merchant_payout_date BETWEEN ? AND ?", [ds[0], ds[-1]]
        ).fetchone()[0])
        act_in = sum(inbound_by_day.get(x.isoformat(), 0.0) for x in ds)
        act_out = float(con.execute(
            "SELECT COALESCE(SUM(gross_amount - reserve_retained_amount),0)"
            " FROM fact_transactions WHERE merchant_payout_date BETWEEN ? AND ?",
            [ds[0], ds[-1]]).fetchone()[0])
        act_net = act_in - act_out
        bud_gpv = budget_daily_gpv * len(ds)
        bud_net = bud_gpv * budget_net_take
        volume = (act_gpv - bud_gpv) * budget_net_take
        timing = act_in - forecast_inbound.get(wk, act_in)
        mix_rows = con.execute(
            "SELECT payment_rail, SUM(gross_amount) FROM fact_transactions"
            " WHERE merchant_payout_date BETWEEN ? AND ? GROUP BY 1",
            [ds[0], ds[-1]]).fetchall()
        mix = 0.0
        if act_gpv > 0:
            for r, g in mix_rows:
                mix = mix + act_gpv * ((float(g) / act_gpv)
                                       - budget_mix.get(r, 0.0)) * budget_take.get(r, 0.0)
        eps = (act_net - bud_net) - (volume + timing + mix)
        out_rows.append((wk, ds[0], ds[-1], act_gpv, bud_gpv, act_net,
                         bud_net, volume, timing, mix, eps))
    con.register("df_twcf_tmp", _pd.DataFrame(out_rows, columns=[
        "week_key", "week_start", "week_end", "actual_gpv", "budget_gpv",
        "actual_net_cash", "budget_net_cash", "volume_variance",
        "timing_variance", "mix_variance", "residual_eps"]))
    con.execute("DELETE FROM fpa_twcf_weekly_variance")
    con.execute("INSERT INTO fpa_twcf_weekly_variance SELECT * FROM df_twcf_tmp")
    con.unregister("df_twcf_tmp")
    return con.execute("SELECT * FROM fpa_twcf_weekly_variance ORDER BY week_key").df()
