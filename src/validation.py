"""Focused constraint audit (CHECKs are re-verified here: DuckDB parses but
does not reliably enforce them, and FK enforcement is limited; orphans and
domain violations are rejected by this function, not by DDL alone)."""
import pandas as pd

RAILS = frozenset({
    "CARD_VISA", "CARD_MC", "CARD_AMEX",
    "ACH_STANDARD", "ACH_SAME_DAY", "RTP_FEDNOW",
})
TIERS = frozenset({"TIER_1", "TIER_2", "TIER_3", "TIER_4"})
CONTRACTS = frozenset({"NEXT_DAY_T1", "SAME_DAY_RTP", "TWO_DAY_T2"})
LCR_STATUS = frozenset({"COMPLIANT", "WARNING", "BREACH"})


def validate(con):
    issues = []
    cal = con.execute("SELECT * FROM dim_calendar ORDER BY calendar_date").df()
    if cal["calendar_date"].duplicated().any():
        issues.append("dim_calendar: duplicate calendar_date")
    if cal["calendar_date"].isna().any() or cal["next_banking_day_us"].isna().any():
        issues.append("dim_calendar: null date key")
    if len(cal[cal["is_weekend"] & cal["is_banking_day_us"]]):
        issues.append("dim_calendar: weekend rows flagged is_banking_day_us")
    if len(cal[cal["is_weekend"] & cal["is_banking_day_eu"]]):
        issues.append("dim_calendar: weekend rows flagged is_banking_day_eu")
    lut = dict(zip(pd.to_datetime(cal["calendar_date"]).dt.strftime("%Y-%m-%d"),
                   cal["is_banking_day_us"]))
    for _, r in cal.iterrows():
        key = pd.to_datetime(r["calendar_date"]).strftime("%Y-%m-%d")
        nxt = pd.to_datetime(r["next_banking_day_us"]).strftime("%Y-%m-%d")
        if not lut.get(nxt, False):
            issues.append(f"dim_calendar: next_banking_day_us {nxt} not a US banking day")
            break
        if key > nxt:
            issues.append("dim_calendar: next_banking_day_us goes backwards")
            break
    m = con.execute("SELECT * FROM dim_merchant").df()
    if m["merchant_id"].duplicated().any():
        issues.append("dim_merchant: duplicate merchant_id")
    if len(m) and (~m["risk_tier"].isin(TIERS)).any():
        issues.append("dim_merchant: risk_tier outside TIER_1..TIER_4")
    if len(m) and (~m["payout_contract_type"].isin(CONTRACTS)).any():
        issues.append("dim_merchant: payout_contract_type outside domain")
    if len(m) and (m["mcc_code"].isna().any()
                   or (m["mcc_code"].astype(str).str.len() != 4).any()):
        issues.append("dim_merchant: mcc_code must be 4 chars")
    t = con.execute("SELECT * FROM fact_transactions").df()
    if len(t):
        if t["transaction_id"].duplicated().any():
            issues.append("fact_transactions: duplicate transaction_id")
        orphan = con.execute(
            "SELECT COUNT(*) FROM fact_transactions t LEFT JOIN dim_merchant m "
            "ON t.merchant_id = m.merchant_id WHERE m.merchant_id IS NULL"
        ).fetchone()[0]
        if orphan:
            issues.append(f"fact_transactions: {orphan} orphan merchant_id rows")
        if (~t["payment_rail"].isin(RAILS)).any():
            issues.append("fact_transactions: payment_rail outside 6-rail domain")
        for col in ("gross_amount", "scheme_interchange_cost",
                    "processor_fee", "reserve_retained_amount"):
            if (t[col].astype(float) < -1e-9).any():
                issues.append(f"fact_transactions: negative {col}")
        if ((t["reserve_retained_amount"].astype(float)
             - t["gross_amount"].astype(float)) > 1e-9).any():
            issues.append("fact_transactions: reserve exceeds own gross (pool segregation)")
        if ((pd.to_datetime(t["merchant_payout_date"])
             < pd.to_datetime(t["auth_date"])).any()
                or (pd.to_datetime(t["inbound_settlement_date"])
                    < pd.to_datetime(t["auth_date"])).any()):
            issues.append("fact_transactions: settlement date precedes auth_date")
    for tbl in ("fpa_cash_waterfall_daily", "fpa_regulatory_liquidity_daily"):
        d = con.execute(f"SELECT * FROM {tbl}").df()
        if d["ledger_date"].duplicated().any():
            issues.append(f"{tbl}: duplicate ledger_date")
    r = con.execute("SELECT * FROM fpa_regulatory_liquidity_daily").df()
    if len(r) and (~r["lcr_status"].isin(LCR_STATUS)).any():
        issues.append("fpa_regulatory_liquidity_daily: lcr_status outside domain")
    return issues
