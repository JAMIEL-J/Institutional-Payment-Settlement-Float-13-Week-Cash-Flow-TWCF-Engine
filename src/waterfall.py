"""Waterfall: constants + daily flow aggregation + engine."""
from decimal import Decimal

from .config import (
    MIN_CORP_LIQUIDITY_COVENANT, TARGET_CORP_LIQUIDITY,
    REVOLVER_CAPACITY, OPENING_CORP_CASH,
)

MACRO_PARAMS = {
    "BASELINE": {"sofr": Decimal("0.0425"), "spread": Decimal("0.0200")},
    "ADVERSE": {"sofr": Decimal("0.0575"), "spread": Decimal("0.0275")},
    "SEVERELY_ADVERSE": {"sofr": Decimal("0.0700"), "spread": Decimal("0.0375")},
}

PD_LGD = {
    "BASELINE": {"pd": Decimal("0.002"), "lgd": Decimal("0.50")},
    "ADVERSE": {"pd": Decimal("0.011"), "lgd": Decimal("0.70")},
    "SEVERELY_ADVERSE": {"pd": Decimal("0.035"), "lgd": Decimal("0.85")},
}

BURN_IN_DAYS = 7
MONTHLY_CORPORATE_OPEX = Decimal("50000000.00")

LAG_SHIFT_DAYS = {
    "BASELINE": 0,
    "ADVERSE": 1,
    "SEVERELY_ADVERSE": 2,
}


def _lag(scenario):
    return LAG_SHIFT_DAYS[scenario]


def daily_flows(con, start, end, lag_shift_days=0):
    if lag_shift_days:
        return con.execute(
            "WITH inbound AS ("
            " SELECT CAST(inbound_settlement_date + ? AS DATE) AS d,"
            " SUM(gross_amount) AS inbound_gross,"
            " SUM(scheme_interchange_cost) AS scheme_costs"
            " FROM fact_transactions GROUP BY 1),"
            " outbound AS ("
            " SELECT merchant_payout_date AS d,"
            " SUM(gross_amount - reserve_retained_amount) AS payout_net,"
            " SUM(processor_fee - scheme_interchange_cost) AS net_revenue,"
            " SUM(gross_amount) AS auth_gpv"
            " FROM fact_transactions"
            " WHERE merchant_payout_date BETWEEN ? AND ? GROUP BY 1)"
            " SELECT CAST(c.calendar_date AS VARCHAR) AS ledger_date,"
            " COALESCE(i.inbound_gross, 0), COALESCE(i.scheme_costs, 0),"
            " COALESCE(o.payout_net, 0), COALESCE(o.net_revenue, 0),"
            " COALESCE(o.auth_gpv, 0)"
            " FROM dim_calendar c"
            " LEFT JOIN inbound i ON i.d = c.calendar_date"
            " LEFT JOIN outbound o ON o.d = c.calendar_date"
            " WHERE c.calendar_date BETWEEN ? AND ?"
            " ORDER BY c.calendar_date",
            [lag_shift_days, start, end, start, end]).fetchall()
    return con.execute(
        "WITH inbound AS ("
        " SELECT inbound_settlement_date AS d,"
        " SUM(gross_amount) AS inbound_gross,"
        " SUM(scheme_interchange_cost) AS scheme_costs"
        " FROM fact_transactions"
        " WHERE inbound_settlement_date BETWEEN ? AND ? GROUP BY 1),"
        " outbound AS ("
        " SELECT merchant_payout_date AS d,"
        " SUM(gross_amount - reserve_retained_amount) AS payout_net,"
        " SUM(processor_fee - scheme_interchange_cost) AS net_revenue,"
        " SUM(gross_amount) AS auth_gpv"
        " FROM fact_transactions"
        " WHERE merchant_payout_date BETWEEN ? AND ? GROUP BY 1)"
        " SELECT CAST(c.calendar_date AS VARCHAR) AS ledger_date,"
        " COALESCE(i.inbound_gross, 0), COALESCE(i.scheme_costs, 0),"
        " COALESCE(o.payout_net, 0), COALESCE(o.net_revenue, 0),"
        " COALESCE(o.auth_gpv, 0)"
        " FROM dim_calendar c"
        " LEFT JOIN inbound i ON i.d = c.calendar_date"
        " LEFT JOIN outbound o ON o.d = c.calendar_date"
        " WHERE c.calendar_date BETWEEN ? AND ?"
        " ORDER BY c.calendar_date",
        [start, end, start, end, start, end]).fetchall()



def execute_daily_waterfall_engine(con, macro_scenario="BASELINE", start=None, end=None):
    import datetime as _dt
    import pandas as _pd
    from decimal import Decimal as _D, ROUND_HALF_UP as _H
    from .config import CAL_START as _S
    if macro_scenario not in MACRO_PARAMS:
        raise ValueError("unknown macro_scenario")
    rate = MACRO_PARAMS[macro_scenario]["sofr"] + MACRO_PARAMS[macro_scenario]["spread"]
    if start is None:
        start = _S
    if end is None:
        end = start + _dt.timedelta(days=149)
    burn_in_start = start - _dt.timedelta(days=BURN_IN_DAYS)
    rows = daily_flows(con, burn_in_start, end, lag_shift_days=_lag(macro_scenario))
    corp = OPENING_CORP_CASH
    debt = _D("0.00")
    saf = _D("0.00")
    allow = _D("0.00")
    wf_rows, liq_rows = [], []
    def q2(x):
        return _D(str(x)).quantize(_D("0.01"), rounding=_H)
    for ledger_date_str, inbound, scheme, payout, revenue, gpv in rows:
        ledger_date = _dt.date.fromisoformat(str(ledger_date_str))
        in_d, sc_d, out_d, rev_d = q2(inbound), q2(scheme), q2(payout), q2(revenue)
        saf_open = saf
        saf = saf_open + in_d
        injection = max(_D("0.00"), out_d - saf)
        saf = saf + injection - out_d
        earned_sweep = rev_d + sc_d
        if saf >= earned_sweep:
            saf = saf - earned_sweep
        else:
            earned_sweep = saf
            saf = _D("0.00")
        fdelta = in_d - out_d - sc_d
        corp_open = corp
        pre = corp_open + rev_d - injection
        draw = _D("0.00")
        repay = _D("0.00")
        if pre < MIN_CORP_LIQUIDITY_COVENANT:
            draw = min(MIN_CORP_LIQUIDITY_COVENANT - pre, REVOLVER_CAPACITY - debt)
            debt = debt + draw
            pre = pre + draw
        elif pre > TARGET_CORP_LIQUIDITY and debt > 0:
            repay = min(pre - TARGET_CORP_LIQUIDITY, debt)
            debt = debt - repay
            pre = pre - repay
        interest = (debt * rate / _D(360)).quantize(_D("0.01"), rounding=_H)
        corp = pre - interest
        if ledger_date >= start:
            charge = (q2(gpv) * PD_LGD[macro_scenario]["pd"]
                      * PD_LGD[macro_scenario]["lgd"]).quantize(_D("0.01"), rounding=_H)
            allow = allow + charge
            wf_rows.append((ledger_date, float(saf_open), float(in_d), float(out_d),
                            float(fdelta), float(injection), float(corp_open), float(rev_d),
                            float(pre), float(draw), float(repay), float(debt),
                            float(interest), float(corp)))
            historical_peak_injection = max([r[5] for r in wf_rows[-30:]] or [0.0])
            monthly_debt_service = (debt * rate / _D(12)).quantize(_D("0.01"), rounding=_H)
            denom = (_D(str(historical_peak_injection))
                     + MONTHLY_CORPORATE_OPEX
                     + monthly_debt_service)
            if denom > 0:
                ratio = (corp / denom).quantize(_D("0.0001"), rounding=_H)
                if ratio > _D("999.9999"):
                    ratio = _D("999.9999")
                status = "COMPLIANT" if ratio >= _D("1.00") else "BREACH"
            else:
                ratio = _D("999.0000")
                status = "COMPLIANT"
            cushion = corp + (REVOLVER_CAPACITY - debt) - MIN_CORP_LIQUIDITY_COVENANT
            liq_rows.append((ledger_date, float(corp), float(denom), float(ratio),
                             status, float(allow), float(cushion)))
    cols = ["ledger_date", "safeguarded_opening_cash", "safeguarded_inbound_settlements",
            "safeguarded_outbound_payouts", "safeguarded_net_float_delta",
            "corporate_subordination_injection", "corporate_opening_cash",
            "net_revenue_swept", "pre_financing_corporate_cash", "revolver_draw_amount",
            "revolver_repayment_amount", "active_debt_balance",
            "daily_interest_expense", "corporate_closing_cash"]
    con.register("df_wf_tmp", _pd.DataFrame(wf_rows, columns=cols))
    con.execute("DELETE FROM fpa_cash_waterfall_daily")
    con.execute("INSERT INTO fpa_cash_waterfall_daily SELECT * FROM df_wf_tmp")
    con.unregister("df_wf_tmp")
    con.register("df_liq_tmp", _pd.DataFrame(liq_rows, columns=[
        "ledger_date", "total_hqla_level1", "stressed_30d_net_outflows",
        "lcr_ratio", "lcr_status", "cecl_daily_allowance", "covenant_liquidity_cushion"]))
    con.execute("DELETE FROM fpa_regulatory_liquidity_daily")
    con.execute("INSERT INTO fpa_regulatory_liquidity_daily SELECT * FROM df_liq_tmp")
    con.unregister("df_liq_tmp")
    return con.execute("SELECT * FROM fpa_cash_waterfall_daily ORDER BY ledger_date").df()
