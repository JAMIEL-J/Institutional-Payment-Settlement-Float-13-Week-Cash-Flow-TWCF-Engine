"""Transaction normalization + generation (Phase 2, part 1: tables).

Grain-level design (closes I-02): 12 anchor merchants x 6 rails =
72 txns/day written to fact_transactions, so tiers, contracts, and
MCC-level CECL stay testable per the PRD dictionaries.
"""
from src.routing import inbound_date

from .config import RISK_TIER_RESERVE

RAIL_SHARE = {
    "CARD_VISA": 0.44,
    "CARD_MC": 0.30,
    "CARD_AMEX": 0.15,
    "ACH_STANDARD": 0.07,
    "ACH_SAME_DAY": 0.03,
    "RTP_FEDNOW": 0.01,
}
RAIL_TAKE = {
    "CARD_VISA": 0.0275,
    "CARD_MC": 0.0275,
    "CARD_AMEX": 0.0315,
    "ACH_STANDARD": 0.0080,
    "ACH_SAME_DAY": 0.0080,
    "RTP_FEDNOW": 0.0050,
}
RAIL_COST = {
    "CARD_VISA": 0.0180,
    "CARD_MC": 0.0185,
    "CARD_AMEX": 0.0220,
    "ACH_STANDARD": 0.0020,
    "ACH_SAME_DAY": 0.0020,
    "RTP_FEDNOW": 0.0010,
}

ANCHOR_MERCHANTS = [
    ("m-t1-t1", "5411", "TIER_1", "NEXT_DAY_T1"),
    ("m-t1-rtp", "5812", "TIER_1", "SAME_DAY_RTP"),
    ("m-t1-t2", "4111", "TIER_1", "TWO_DAY_T2"),
    ("m-t2-t1", "5411", "TIER_2", "NEXT_DAY_T1"),
    ("m-t2-rtp", "5812", "TIER_2", "SAME_DAY_RTP"),
    ("m-t2-t2", "4111", "TIER_2", "TWO_DAY_T2"),
    ("m-t3-t1", "4511", "TIER_3", "NEXT_DAY_T1"),
    ("m-t3-rtp", "5967", "TIER_3", "SAME_DAY_RTP"),
    ("m-t3-t2", "4511", "TIER_3", "TWO_DAY_T2"),
    ("m-t4-t1", "7995", "TIER_4", "NEXT_DAY_T1"),
    ("m-t4-rtp", "7995", "TIER_4", "SAME_DAY_RTP"),
    ("m-t4-t2", "7995", "TIER_4", "TWO_DAY_T2"),
]



def seed_merchants(con):
    for mid, mcc, tier, contract in ANCHOR_MERCHANTS:
        con.execute("INSERT INTO dim_merchant VALUES (?, ?, ?, ?)",
                    [mid, mcc, tier, contract])


def normalize_merchant_row(merchant_id, mcc_code, risk_tier, payout_contract_type):
    """Validate + normalize one merchant row. Raises ValueError."""
    if risk_tier not in RISK_TIER_RESERVE:
        raise ValueError(f"risk_tier {risk_tier} outside TIER_1..TIER_4")
    if payout_contract_type not in ("NEXT_DAY_T1", "SAME_DAY_RTP", "TWO_DAY_T2"):
        raise ValueError(f"payout_contract_type {payout_contract_type} unknown")
    if not (isinstance(mcc_code, str) and len(mcc_code) == 4 and mcc_code.isdigit()):
        raise ValueError(f"mcc_code {mcc_code!r} must be 4 digits")
    return (merchant_id, mcc_code, risk_tier, payout_contract_type)


def route_transaction(auth_date, contract, rail, banking_days):
    from .routing import payout_date, inbound_date
    return (payout_date(auth_date, contract, banking_days),
            inbound_date(auth_date, rail, banking_days))


def generate_synthetic_transactions(con, scale_daily_gpv=None,
                                    num_days=150, start=None):
    """Deterministic grain generation. Returns row count written."""
    import datetime as dt
    import pandas as pd
    import numpy as np
    from .config import (BASELINE_DAILY_GPV, WEEKEND_VOLUME_MULTIPLIER,
                         GENERATION_SEED, RISK_TIER_RESERVE,
                         CAL_START)
    from .routing import build_us_banking_set, payout_date, inbound_date
    from decimal import Decimal, ROUND_HALF_UP
    if scale_daily_gpv is None:
        scale_daily_gpv = BASELINE_DAILY_GPV
    rng = np.random.default_rng(GENERATION_SEED)
    banking_days = build_us_banking_set(con)
    have = con.execute("SELECT COUNT(*) FROM dim_merchant").fetchone()[0]
    if have < len(ANCHOR_MERCHANTS):
        raise RuntimeError("seed_merchants(con) must run before generation")
    merchants = {r[0]: r for r in con.execute(
        "SELECT merchant_id, mcc_code, risk_tier, payout_contract_type "
        "FROM dim_merchant").fetchall()}
    if start is None:
        start = CAL_START
    noise = rng.normal(1.0, 0.03, num_days)
    rails = list(RAIL_SHARE)
    seq = 0
    rows = []
    for day in range(num_days):
        auth = start + dt.timedelta(days=day)
        mult = WEEKEND_VOLUME_MULTIPLIER if auth.weekday() in (4, 5, 6) else 1.0
        daily_gpv = scale_daily_gpv * mult * float(noise[day])
        cells = [(m[0], r) for m in ANCHOR_MERCHANTS for r in rails]
        weights = [(1.0 / len(ANCHOR_MERCHANTS)) * RAIL_SHARE[r] for _, r in cells]
        exact = [Decimal(str(daily_gpv)) * Decimal(str(w)) for w in weights]
        cents = [int((e * 100).to_integral_value(rounding=ROUND_HALF_UP))
                 for e in exact]
        target_cents = int((Decimal(str(daily_gpv)) * 100).to_integral_value(
            rounding=ROUND_HALF_UP))
        diff = target_cents - sum(cents)
        if diff:
            order = sorted(range(len(cells)),
                           key=lambda i: exact[i] - Decimal(cents[i]) / 100,
                           reverse=(diff > 0))
            for i in order[:abs(diff)]:
                cents[i] += 1 if diff > 0 else -1
        for (mid, rail), gc in zip(cells, cents):
            if gc <= 0:
                continue
            gross = Decimal(gc) / 100
            tier = merchants[mid][2]
            contract = merchants[mid][3]
            rate = RISK_TIER_RESERVE[tier][0]
            reserve = (gross * rate).quantize(Decimal("0.01"),
                                             rounding=ROUND_HALF_UP)
            cost = (gross * Decimal(str(RAIL_COST[rail]))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP)
            fee = (gross * Decimal(str(RAIL_TAKE[rail]))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP)
            pdate = payout_date(auth, contract, banking_days)
            sdate = inbound_date(auth, rail, banking_days)
            seq += 1
            rows.append((f"t-{auth.isoformat()}-{seq:06d}", mid,
                         dt.datetime(auth.year, auth.month, auth.day, 10, 0, 0),
                         auth, rail, float(gross), float(cost),
                         float(fee), float(reserve), pdate, sdate))
    con.register("df_gen_tmp",
                 pd.DataFrame(rows, columns=[
                     "transaction_id", "merchant_id", "auth_timestamp",
                     "auth_date", "payment_rail", "gross_amount",
                     "scheme_interchange_cost", "processor_fee",
                     "reserve_retained_amount", "merchant_payout_date",
                     "inbound_settlement_date"]))
    con.execute("INSERT INTO fact_transactions SELECT * FROM df_gen_tmp")
    con.unregister("df_gen_tmp")
    return seq
