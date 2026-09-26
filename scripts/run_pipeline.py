"""Standalone CLI runner for the Institutional Settlement Float & TWCF Engine.

Executes the end-to-end simulation across any chosen macro scenario:
- Database initialization and calendar generation
- Anchor merchant seeding and synthetic transaction generation
- Daily dual-ledger cash waterfall execution
- 13-Week Cash Flow (TWCF) variance decomposition
- Summary KPI benchmarks matching PRD Section 7 & 8

Usage:
    python scripts/run_pipeline.py --scenario BASELINE --days 150
    python scripts/run_pipeline.py --scenario ADVERSE --days 150
    python scripts/run_pipeline.py --scenario SEVERELY_ADVERSE --days 150
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import initialize_database
from src.transactions import seed_merchants, generate_synthetic_transactions
from src.waterfall import execute_daily_waterfall_engine
from src.twcf import weekly_variance
from src.dashboard import build_dashboard_frames, HEADROOM_ALERT, COVENANT_FLOOR


def run_pipeline(scenario="BASELINE", days=150, gpv_daily=600_000_000.0):
    print("=" * 70)
    print(f"INSTITUTIONAL SETTLEMENT FLOAT & 13W CASH FLOW ENGINE")
    print(f"Scenario: {scenario} | Projection Horizon: {days} Days | Base GPV: ${gpv_daily:,.0f}/day")
    print("=" * 70)

    # 1. Initialize DB & schemas
    print("[1/5] Initializing database and banking calendar (US Fed + ECB T2)...")
    con = initialize_database()

    # 2. Seed merchants & transactions
    print("[2/5] Seeding 12 anchor merchants and generating normalized transactions...")
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=gpv_daily, num_days=days)

    # 3. Waterfall execution
    print(f"[3/5] Executing daily dual-ledger cash waterfall ({scenario})...")
    df_wf = execute_daily_waterfall_engine(con, macro_scenario=scenario)

    # 4. TWCF variance
    print("[4/5] Computing rolling 13-week TWCF variance decomposition...")
    df_twcf = weekly_variance(con)

    # 5. Dashboard frames & KPI benchmarks
    print("[5/5] Extracting executive benchmarks and BI frames...")
    frames = build_dashboard_frames(con, scenario)

    t1 = frames["tab1"]
    t2 = frames["tab2"]
    t3 = frames["tab3"]
    t4 = frames["tab4"]

    final_cash = df_wf["corporate_closing_cash"].iloc[-1]
    peak_revolver = df_wf["active_debt_balance"].max()
    total_interest = df_wf["daily_interest_expense"].sum()
    min_lcr = con.execute("SELECT MIN(lcr_ratio) FROM fpa_regulatory_liquidity_daily").fetchone()[0]

    print("\n" + "-" * 70)
    print("EXECUTIVE BENCHMARK SUMMARY (PRD Sections 7 & 8)")
    print("-" * 70)
    print(f"  Final Corporate Cash:               ${final_cash:,.2f}")
    print(f"  Peak Revolver Debt Utilization:     ${peak_revolver:,.2f} / $500,000,000.00")
    print(f"  Total Period Interest Expense Drag: ${total_interest:,.2f}")
    print(f"  Effective Borrowing Cost:           {t2['rate']:.2%} (SOFR + Spread)")
    print(f"  Minimum Basel III LCR:              {float(min_lcr):.2%}")
    print(f"  Current Basel III LCR Status:       {t1['lcr_status']} ({t1['lcr_ratio']:.2%})")
    print(f"  Total Liquidity Cushion:            ${t1['cushion']:,.2f}")
    print(f"  Covenant Headroom vs $250M Floor:   ${t1['covenant_headroom']:,.2f}")
    print(f"  Covenant Alert (<$50M Headroom):    {'*** ALERT ACTIVE ***' if t1['alert'] else 'Compliant'}")
    print(f"  Days Float Outstanding (DFO):       {t3['dfo']:.2f} days")
    print(f"  Settlements Receivable (Asset):     ${t3['receivables']:,.2f}")
    print(f"  Customers Payable (Liability):      ${t3['payables']:,.2f}")
    print(f"  Active TWCF Weeks Evaluated:        {len(t4)} weeks")
    print("-" * 70 + "\n")

    con.close()
    return {
        "final_cash": final_cash,
        "peak_revolver": peak_revolver,
        "total_interest": total_interest,
        "min_lcr": float(min_lcr),
        "dfo": t3["dfo"],
    }


def main():
    parser = argparse.ArgumentParser(description="Institutional Cash Flow & Settlement Pipeline")
    parser.add_argument("--scenario", default="BASELINE", choices=["BASELINE", "ADVERSE", "SEVERELY_ADVERSE"],
                        help="Macroeconomic scenario to evaluate")
    parser.add_argument("--days", type=int, default=150, help="Number of projection days")
    parser.add_argument("--gpv", type=float, default=600_000_000.0, help="Daily GPV baseline scale")
    args = parser.parse_args()

    run_pipeline(scenario=args.scenario, days=args.days, gpv_daily=args.gpv)


if __name__ == "__main__":
    main()

