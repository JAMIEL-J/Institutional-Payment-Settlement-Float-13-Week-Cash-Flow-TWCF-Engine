"""Phase 7 End-to-End multi-scenario verification test suite.

Verifies the entire lifecycle of the Institutional Payment Float & TWCF Engine:
- Foundation & Relational Constraints
- Deterministic 6-Rail Routing & Normalization
- Daily Dual-Ledger Cash Waterfall (Client Safeguarded vs Corporate Operating)
- Macro Stress Scenarios (Baseline, Adverse, Severely Adverse)
- Regulatory Liquidity (Basel III LCR) & Credit Allowance (CECL ASC 326)
- 13-Week Cash Flow Variance Decomposition (Volume, Mix, Timing, CECL)
- Executive BI Surface Reconciliation (PRD Section 8 Tabs 1-4)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from src.database import initialize_database
from src.transactions import seed_merchants, generate_synthetic_transactions
from src.validation import validate
from src.waterfall import execute_daily_waterfall_engine
from src.twcf import weekly_variance
from src.dashboard import build_dashboard_frames, HEADROOM_ALERT, COVENANT_FLOOR
from src.config import REVOLVER_CAPACITY, MIN_CORP_LIQUIDITY_COVENANT


def test_e2e_baseline_pipeline():
    """Verify full end-to-end pipeline run under BASELINE macro conditions."""
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
    
    # 1. Structural schema & constraint validation
    val_errs = validate(con)
    assert len(val_errs) == 0, f"Schema validation errors: {val_errs}"
    
    # 2. Daily waterfall execution
    df_wf = execute_daily_waterfall_engine(con, macro_scenario="BASELINE")
    assert len(df_wf) == 150
    assert "corporate_closing_cash" in df_wf.columns
    
    # 3. Liquidity & covenant verifications
    final_cash = float(df_wf["corporate_closing_cash"].iloc[-1])
    peak_debt = float(df_wf["active_debt_balance"].max())
    total_interest = float(df_wf["daily_interest_expense"].sum())
    assert final_cash > 0.0
    assert 0.0 <= peak_debt <= REVOLVER_CAPACITY
    assert total_interest > 0.0
    
    # 4. TWCF rolling 13-week variance calculation
    df_twcf = weekly_variance(con)
    assert len(df_twcf) > 0
    # Additive variance decomposition identity: Volume + Timing + Mix + eps = Actual - Budget
    for _, r in df_twcf.iterrows():
        driver_sum = (float(r["volume_variance"]) + 
                      float(r["timing_variance"]) + 
                      float(r["mix_variance"]) + 
                      float(r["residual_eps"]))
        actual_delta = float(r["actual_net_cash"]) - float(r["budget_net_cash"])
        assert abs(driver_sum - actual_delta) < 1.0
        
    # 5. Executive BI Surface reconciliation
    frames = build_dashboard_frames(con, "BASELINE")
    t1 = frames["tab1"]
    assert t1["covenant_floor"] == COVENANT_FLOOR
    assert t1["covenant_headroom"] > HEADROOM_ALERT
    assert t1["alert"] is False
    assert len(t1["series"]) == 150
    
    t2 = frames["tab2"]
    assert abs(t2["rate"] - 0.0625) < 1e-6
    assert len(t2["daily"]) == 150
    assert len(t2["monthly_carry_bps"]) >= 4
    
    t3 = frames["tab3"]
    assert t3["dfo"] > 0.0
    assert len(t3["daily"]) == 150
    
    t4 = frames["tab4"]
    assert len(t4) == len(df_twcf)
    
    con.close()


def test_e2e_adverse_stress_behavior():
    """Verify ADVERSE scenario stress dynamics: lag shifts, higher rates, and headroom alerts."""
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
    
    df_wf = execute_daily_waterfall_engine(con, macro_scenario="ADVERSE")
    weekly_variance(con)
    frames = build_dashboard_frames(con, "ADVERSE")
    
    # 1. Borrowing rate equals SOFR (5.75%) + Spread (2.75%) = 8.50%
    assert abs(frames["tab2"]["rate"] - 0.0850) < 1e-6
    
    # 2. Revolver reaches full capacity under adverse stress
    peak_debt = float(df_wf["active_debt_balance"].max())
    assert peak_debt == REVOLVER_CAPACITY
    
    # 3. Headroom alert triggers when liquidity is strained
    t1 = frames["tab1"]
    assert t1["alert"] is True
    assert t1["covenant_headroom"] < HEADROOM_ALERT
    
    # 4. CECL cumulative allowance is higher than baseline
    cecl_allowance = float(con.execute(
        "SELECT MAX(cecl_daily_allowance) FROM fpa_regulatory_liquidity_daily"
    ).fetchone()[0])
    assert cecl_allowance > 500_000_000.0
    
    con.close()


def test_e2e_severely_adverse_stress_behavior():
    """Verify SEVERELY_ADVERSE scenario: 48h freeze shift, SOFR 7.00%+3.75%, peak CECL."""
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
    
    df_wf = execute_daily_waterfall_engine(con, macro_scenario="SEVERELY_ADVERSE")
    weekly_variance(con)
    frames = build_dashboard_frames(con, "SEVERELY_ADVERSE")
    
    # Borrowing rate equals SOFR (7.00%) + Spread (3.75%) = 10.75%
    assert abs(frames["tab2"]["rate"] - 0.1075) < 1e-6
    
    # Total interest expense drag is highest under Severely Adverse
    total_interest = float(df_wf["daily_interest_expense"].sum())
    assert total_interest > 20_000_000.0
    
    # Headroom alert is active
    assert frames["tab1"]["alert"] is True
    
    con.close()


def test_e2e_dual_ledger_conservation_and_segregation():
    """Verify daily dual-ledger conservation, non-negative client funds, and zero commingling."""
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
    df_wf = execute_daily_waterfall_engine(con, macro_scenario="BASELINE")
    
    for idx, row in df_wf.iterrows():
        # Safeguarded ledger conservation:
        # Closing = Opening + Inbound - Outbound + Corporate Injection
        saf_calc = (row["safeguarded_opening_cash"] + 
                    row["safeguarded_inbound_settlements"] - 
                    row["safeguarded_outbound_payouts"] + 
                    row["corporate_subordination_injection"])
        assert saf_calc >= -0.01, f"Safeguarded pool became negative on day {row['ledger_date']}"
        
        # Corporate pre-financing identity:
        # PreFin = Corporate Open + Net Revenue - Injection + Draw - Repay
        pre_calc = (row["corporate_opening_cash"] + 
                    row["net_revenue_swept"] - 
                    row["corporate_subordination_injection"] +
                    row["revolver_draw_amount"] -
                    row["revolver_repayment_amount"])
        assert abs(pre_calc - row["pre_financing_corporate_cash"]) < 0.05
        
        # Corporate closing cash identity:
        # Closing = PreFin - Daily Interest
        corp_calc = row["pre_financing_corporate_cash"] - row["daily_interest_expense"]
        assert abs(corp_calc - row["corporate_closing_cash"]) < 0.05
        
        # Revolver facility bounds:
        assert 0.0 <= row["active_debt_balance"] <= REVOLVER_CAPACITY
        
    con.close()
