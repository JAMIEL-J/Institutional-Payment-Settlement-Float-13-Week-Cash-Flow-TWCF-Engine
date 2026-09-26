"""Scenario parameters, CECL, LCR, covenant and leverage checks (Phase 4).

Thin wrappers over the waterfall engine constants so tests can address
the Phase 4 surface directly. Canonical values live in waterfall.py.
"""
from decimal import Decimal, ROUND_HALF_UP

from .config import MIN_CORP_LIQUIDITY_COVENANT, REVOLVER_CAPACITY
from .waterfall import MACRO_PARAMS, PD_LGD, LAG_SHIFT_DAYS


LCR_RUNOFF = Decimal("0.30")
LCR_WARN = Decimal("1.05")
LCR_MIN = Decimal("1.00")
LEVERAGE_MAX = Decimal("3.0")

_C2 = Decimal("0.01")
_C4 = Decimal("0.0001")


def _check_scenario(scenario):
    if scenario not in MACRO_PARAMS or scenario not in PD_LGD:
        raise ValueError(f"unknown macro_scenario {scenario!r}")


def borrowing_rate(scenario):
    _check_scenario(scenario)
    return MACRO_PARAMS[scenario]["sofr"] + MACRO_PARAMS[scenario]["spread"]


def daily_interest_expense(drawn_principal, scenario):
    _check_scenario(scenario)
    return (Decimal(drawn_principal) * borrowing_rate(scenario)
            / Decimal(360)).quantize(_C2, rounding=ROUND_HALF_UP)


def cecl_daily_charge(auth_gpv, scenario, fraud_allocation=0):
    _check_scenario(scenario)
    p = PD_LGD[scenario]
    return (Decimal(auth_gpv) * p["pd"] * p["lgd"]
            + Decimal(fraud_allocation)).quantize(_C2, rounding=ROUND_HALF_UP)


def lcr_for_day(hqla_level1, avg_daily_payout):
    hqla = Decimal(hqla_level1)
    outflows = (Decimal(avg_daily_payout) * Decimal(30)
                * LCR_RUNOFF).quantize(_C2, rounding=ROUND_HALF_UP)
    if outflows <= 0:
        return None, outflows, "COMPLIANT"
    ratio = (hqla / outflows).quantize(_C4, rounding=ROUND_HALF_UP)
    if ratio >= LCR_WARN:
        status = "COMPLIANT"
    elif ratio >= LCR_MIN:
        status = "WARNING"
    else:
        status = "BREACH"
    return ratio, outflows, status


def covenant_breach(corporate_cash, active_debt):
    total = Decimal(corporate_cash) + (REVOLVER_CAPACITY - Decimal(active_debt))
    return total < MIN_CORP_LIQUIDITY_COVENANT


def leverage_ratio(active_debt, unrestricted_cash, ltm_ebitda=None):
    if ltm_ebitda is None or Decimal(ltm_ebitda) <= 0:
        return None
    return ((Decimal(active_debt) - Decimal(unrestricted_cash))
            / Decimal(ltm_ebitda)).quantize(_C4, rounding=ROUND_HALF_UP)


def leverage_breach(active_debt, unrestricted_cash, ltm_ebitda=None):
    ratio = leverage_ratio(active_debt, unrestricted_cash, ltm_ebitda)
    if ratio is None:
        return None
    return ratio > LEVERAGE_MAX


def net_cecl_exposure(cumulative_allowance, rolling_reserve_balance):
    return max(Decimal("0.00"),
               Decimal(cumulative_allowance) - Decimal(rolling_reserve_balance))
