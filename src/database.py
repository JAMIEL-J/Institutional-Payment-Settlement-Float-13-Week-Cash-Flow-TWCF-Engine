"""Relational schemas per PRD 5.1 dictionaries (PRD TEXT governs; I-01..I-03)."""
import duckdb

from .banking_calendar import build_calendar_df

DDL_CAL = """
CREATE TABLE dim_calendar (
    calendar_date DATE PRIMARY KEY,
    day_of_week VARCHAR NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_banking_day_us BOOLEAN NOT NULL,
    is_banking_day_eu BOOLEAN NOT NULL,
    next_banking_day_us DATE NOT NULL
);
"""
DDL_MERCHANT = """
CREATE TABLE dim_merchant (
    merchant_id VARCHAR PRIMARY KEY,
    mcc_code VARCHAR NOT NULL,
    risk_tier VARCHAR NOT NULL,
    payout_contract_type VARCHAR NOT NULL
);
"""
DDL_FACT = """
CREATE TABLE fact_transactions (
    transaction_id VARCHAR PRIMARY KEY,
    merchant_id VARCHAR NOT NULL REFERENCES dim_merchant(merchant_id),
    auth_timestamp TIMESTAMP NOT NULL,
    auth_date DATE NOT NULL,
    payment_rail VARCHAR NOT NULL,
    gross_amount DECIMAL(14,2) NOT NULL,
    scheme_interchange_cost DECIMAL(12,4) NOT NULL,
    processor_fee DECIMAL(12,4) NOT NULL,
    reserve_retained_amount DECIMAL(12,2) NOT NULL,
    merchant_payout_date DATE NOT NULL,
    inbound_settlement_date DATE NOT NULL
);
"""
DDL_WATERFALL = """
CREATE TABLE fpa_cash_waterfall_daily (
    ledger_date DATE PRIMARY KEY,
    safeguarded_opening_cash DECIMAL(16,2) NOT NULL,
    safeguarded_inbound_settlements DECIMAL(16,2) NOT NULL,
    safeguarded_outbound_payouts DECIMAL(16,2) NOT NULL,
    safeguarded_net_float_delta DECIMAL(16,2) NOT NULL,
    corporate_subordination_injection DECIMAL(16,2) NOT NULL,
    corporate_opening_cash DECIMAL(16,2) NOT NULL,
    net_revenue_swept DECIMAL(14,2) NOT NULL,
    pre_financing_corporate_cash DECIMAL(16,2) NOT NULL,
    revolver_draw_amount DECIMAL(14,2) NOT NULL,
    revolver_repayment_amount DECIMAL(14,2) NOT NULL,
    active_debt_balance DECIMAL(16,2) NOT NULL,
    daily_interest_expense DECIMAL(12,2) NOT NULL,
    corporate_closing_cash DECIMAL(16,2) NOT NULL
);
"""
DDL_LIQUIDITY = """
CREATE TABLE fpa_regulatory_liquidity_daily (
    ledger_date DATE PRIMARY KEY,
    total_hqla_level1 DECIMAL(16,2) NOT NULL,
    stressed_30d_net_outflows DECIMAL(16,2) NOT NULL,
    lcr_ratio DECIMAL(8,4) NOT NULL,
    lcr_status VARCHAR NOT NULL,
    cecl_daily_allowance DECIMAL(14,2) NOT NULL,
    covenant_liquidity_cushion DECIMAL(16,2) NOT NULL
);
"""

DDL = DDL_CAL + DDL_MERCHANT + DDL_FACT + DDL_WATERFALL + DDL_LIQUIDITY


def initialize_database(db_path=":memory:"):
    con = duckdb.connect(database=db_path)
    for stmt in [s for s in DDL.split(";") if s.strip()]:
        con.execute(stmt)
    df_cal = build_calendar_df()
    con.register("df_cal_seed", df_cal)
    con.execute("INSERT INTO dim_calendar SELECT * FROM df_cal_seed")
    return con
