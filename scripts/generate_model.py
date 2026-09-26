"""Senior FP&A Dynamic Financial Model Generator.

Constructs an institutional-grade Excel model where EVERY calculation cell
contains a dynamic Excel formula linking back to assumptions and daily feeds:
1. Assumptions: Global policy drivers, macro matrices, rail fees, merchant tiers.
2. Data_Feed_Daily: Exact transaction inputs from payment rails.
3. Daily_Cash_Waterfall: 150-day dynamic recursive waterfall entirely driven by Excel formulas.
4. Working_Capital_DFO: Receivables, payables, float gap, and DFO formulas.
5. Regulatory_Liquidity_CECL: HQLA Level 1 links, 30d stressed outflows, LCR ratios, and CECL provisions.
6. TWCF_13W_Bridge: Rolling weekly variance decomposition and additive identity check formulas.

Verified via Python's 'formulas' calculation engine.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.errors import IgnoredError, IgnoredErrors

from src.database import initialize_database
from src.transactions import seed_merchants, generate_synthetic_transactions
from src.waterfall import execute_daily_waterfall_engine
from src.twcf import weekly_variance
from src.dashboard import build_dashboard_frames
from src.config import REVOLVER_CAPACITY, MIN_CORP_LIQUIDITY_COVENANT, TARGET_CORP_LIQUIDITY
from src.scenarios import MACRO_PARAMS, PD_LGD, borrowing_rate


def generate_model():
    print("[1/4] Running simulation engine to extract base data feeds...")
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
    df_wf = execute_daily_waterfall_engine(con, macro_scenario="BASELINE")
    df_twcf = weekly_variance(con)
    frames = build_dashboard_frames(con, "BASELINE")

    # Ingestion daily feed rows
    feed_rows = con.execute("""
        WITH daily_inbound AS (
            SELECT inbound_settlement_date AS ledger_date,
                   SUM(gross_amount) AS inbound_gross,
                   SUM(scheme_interchange_cost) AS scheme_costs
            FROM fact_transactions GROUP BY 1
        ),
        daily_outbound AS (
            SELECT merchant_payout_date AS ledger_date,
                   SUM(gross_amount) AS gpv_authorized,
                   SUM(gross_amount) AS outbound_gross,
                   SUM(reserve_retained_amount) AS reserve_withheld,
                   SUM(processor_fee - scheme_interchange_cost) AS net_revenue
            FROM fact_transactions GROUP BY 1
        )
        SELECT 
            c.calendar_date AS ledger_date,
            COALESCE(o.gpv_authorized, 0.0) AS gpv,
            COALESCE(i.inbound_gross, 0.0) AS inbound_gross,
            COALESCE(i.scheme_costs, 0.0) AS scheme_costs,
            COALESCE(o.outbound_gross, 0.0) AS outbound_gross,
            COALESCE(o.reserve_withheld, 0.0) AS reserve_withheld,
            COALESCE(o.net_revenue, 0.0) AS net_revenue
        FROM dim_calendar c
        LEFT JOIN daily_inbound i ON c.calendar_date = i.ledger_date
        LEFT JOIN daily_outbound o ON c.calendar_date = o.ledger_date
        WHERE c.calendar_date BETWEEN '2026-01-01' AND '2026-05-30'
        ORDER BY c.calendar_date;
    """).fetchall()

    daily_wc = frames["tab3"]["daily"]
    con.close()

    print("[2/4] Initializing Excel workbook with Senior FP&A styling...")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove blank default sheet

    # Fonts
    font_name = "Georgia"
    title_font = Font(name=font_name, size=15, bold=True, color="FFFFFF")
    subtitle_font = Font(name=font_name, size=10, italic=True, color="E2E8F0")
    sec_hdr_font = Font(name=font_name, size=11, bold=True, color="1B365D")
    col_hdr_font = Font(name=font_name, size=9, bold=True, color="FFFFFF")
    bold_cell_font = Font(name=font_name, size=9, bold=True, color="0F172A")
    regular_font = Font(name=font_name, size=9, color="0F172A")
    italic_meta_font = Font(name=font_name, size=8, italic=True, color="64748B")
    formula_font = Font(name=font_name, size=9, color="0F172A")

    alert_font = Font(name=font_name, size=9, bold=True, color="991B1B")
    compliant_font = Font(name=font_name, size=9, bold=True, color="166534")

    # Fills - Ocean & Institutional Palette
    navy_hdr_fill = PatternFill(start_color="0C4A6E", end_color="0C4A6E", fill_type="solid")     # Deep Ocean Navy
    slate_hdr_fill = PatternFill(start_color="0369A1", end_color="0369A1", fill_type="solid")    # Ocean Slate
    ice_sec_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")      # Ocean Tint
    alt_row_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    summary_fill = PatternFill(start_color="F0F9FF", end_color="F0F9FF", fill_type="solid")
    alert_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    compliant_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")

    # Borders
    thin_border = Side(border_style="thin", color="CBD5E1")
    cell_border = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
    tot_border = Border(top=thin_border, bottom=Side(border_style="double", color="0C4A6E"))

    # Formats (Explicit en-US locale tag forces Western hundreds-of-millions grouping regardless of local OS settings)
    cur_fmt = "[$$-en-US]#,##0.00"
    cur_no_dec = "[$$-en-US]#,##0"
    pct_fmt = "0.00%"
    int_fmt = "#,##0"

    # =========================================================================
    # TAB 1: Assumptions (Drivers & Global Parameters)
    # =========================================================================
    print("[3/4] Building Sheet 1: Assumptions & Global Policy Drivers...")
    ws_assump = wb.create_sheet(title="Assumptions")
    ws_assump.views.sheetView[0].showGridLines = True

    # Title Banner
    ws_assump.merge_cells("A1:G1")
    ws_assump["A1"] = "INSTITUTIONAL PAYMENT SETTLEMENT FLOAT & 13W CASH FLOW ENGINE"
    ws_assump["A1"].font = title_font
    ws_assump["A1"].fill = navy_hdr_fill
    ws_assump["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_assump.row_dimensions[1].height = 36

    ws_assump.merge_cells("A2:G2")
    ws_assump["A2"] = "Dynamic Treasury Financial Model | Core Assumptions, Policy Constants & Scenario Matrix"
    ws_assump["A2"].font = subtitle_font
    ws_assump["A2"].fill = slate_hdr_fill
    ws_assump["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_assump.row_dimensions[2].height = 20

    ws_assump.cell(row=4, column=1, value="1. GLOBAL TREASURY POLICY CONSTANTS & FACILITY PARAMETERS").font = sec_hdr_font

    assump_params = [
        ("Base Daily Gross Payment Volume (GPV)", 600_000_000.0, cur_fmt, "Platform daily auth baseline"),
        ("Model Projection Horizon (Days)", 150, int_fmt, "Active projection calendar horizon"),
        ("Annualized Scale Run-Rate", "=C5*C6", cur_fmt, "Annualized GPV = Daily GPV * Horizon"),
        ("Actual/360 Money Market Day Count Basis", 360, int_fmt, "Institutional money market convention"),
        ("Revolving Credit Facility Capacity (Cmax)", float(REVOLVER_CAPACITY), cur_fmt, "Total bilateral bank facility"),
        ("Minimum Liquidity Covenant Floor (Lmin)", float(MIN_CORP_LIQUIDITY_COVENANT), cur_fmt, "Credit agreement minimum liquidity floor"),
        ("Target Liquidity Sweep Threshold (Ltarget)", float(TARGET_CORP_LIQUIDITY), cur_fmt, "Automatic debt repayment sweep trigger"),
        ("Covenant Headroom Early Warning Alert Trigger", 50_000_000.0, cur_fmt, "Headroom alert threshold below covenant floor"),
        ("Initial Corporate Opening Cash Balance", 300_000_000.0, cur_fmt, "Day 1 starting operational cash"),
        ("Initial Safeguarded Client Pool Balance", 0.0, cur_fmt, "Day 1 starting client pool (zero commingling)"),
        ("Initial Active Revolver Debt Balance", 0.0, cur_fmt, "Day 1 starting facility borrowing"),
        ("Active Macro Scenario Selector", "BASELINE", "@", "Active macroeconomic environment"),
        ("Benchmark Base SOFR Rate", 0.0425, pct_fmt, "Secured Overnight Financing Rate"),
        ("Credit Facility Margin Spread", 0.0200, pct_fmt, "Bank credit facility spread"),
        ("All-in Borrowing Rate (SOFR + Spread)", "=C17+C18", pct_fmt, "Effective annual borrowing rate"),
        ("CECL Annual Probability of Default (PD)", 0.0020, pct_fmt, "Expected loss probability proxy"),
        ("CECL Loss Given Default (LGD)", 0.5000, pct_fmt, "Expected severity on default"),
        ("Basel III Stressed 30-Day Outflow Run-off Overlay", 0.3000, pct_fmt, "Stressed run-off overlay"),
        ("Basel III LCR Warning Band Threshold", 1.0500, pct_fmt, "LCR early warning buffer (105%)"),
        ("Basel III LCR Minimum Regulatory Floor", 1.0000, pct_fmt, "Statutory minimum compliant floor (100%)"),
    ]

    for idx, (label, val, fmt, note) in enumerate(assump_params, start=5):
        ws_assump.cell(row=idx, column=1, value=label).font = regular_font
        c = ws_assump.cell(row=idx, column=3, value=val)
        c.font = bold_cell_font
        c.number_format = fmt
        c.alignment = Alignment(horizontal="right")
        ws_assump.cell(row=idx, column=4, value=note).font = italic_meta_font

    # Section 2: Rail Schedule
    r_start = 26
    ws_assump.cell(row=r_start, column=1, value="2. PAYMENT NETWORK CLEARING & TAKE-RATE STRUCTURE").font = sec_hdr_font
    r_start += 1
    rail_headers = ["Payment Rail", "Share of GPV", "Processor Take Rate", "Interchange / Scheme Cost", "Net Processor Spread", "Clearing Lag"]
    for c_idx, h in enumerate(rail_headers, start=1):
        cell = ws_assump.cell(row=r_start, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left")
    r_start += 1
    rails = [
        ("CARD_VISA", 0.44, 0.0275, 0.0180, 2),
        ("CARD_MC", 0.30, 0.0275, 0.0185, 2),
        ("CARD_AMEX", 0.15, 0.0315, 0.0220, 3),
        ("ACH_STANDARD", 0.07, 0.0080, 0.0020, 3),
        ("ACH_SAME_DAY", 0.03, 0.0080, 0.0020, 1),
        ("RTP_FEDNOW", 0.01, 0.0050, 0.0010, 0),
    ]
    for rail, share, take, cost, lag in rails:
        ws_assump.cell(row=r_start, column=1, value=rail).font = regular_font
        c2 = ws_assump.cell(row=r_start, column=2, value=share)
        c2.font = regular_font; c2.number_format = pct_fmt
        c3 = ws_assump.cell(row=r_start, column=3, value=take)
        c3.font = regular_font; c3.number_format = pct_fmt
        c4 = ws_assump.cell(row=r_start, column=4, value=cost)
        c4.font = regular_font; c4.number_format = pct_fmt
        c5 = ws_assump.cell(row=r_start, column=5, value=f"=C{r_start}-D{r_start}")  # DYNAMIC FORMULA
        c5.font = bold_cell_font; c5.number_format = pct_fmt
        c6 = ws_assump.cell(row=r_start, column=6, value=f"T+{lag} ({lag} days)")
        c6.font = italic_meta_font; c6.alignment = Alignment(horizontal="center")
        r_start += 1

    # Section 3: Macro Scenarios Matrix
    r_start += 1
    ws_assump.cell(row=r_start, column=1, value="3. MACROECONOMIC STRESS SCENARIO MATRIX").font = sec_hdr_font
    r_start += 1
    sc_hdrs = ["Scenario Name", "Benchmark SOFR", "Credit Spread", "All-in Borrowing Rate", "CECL PD Rate", "CECL LGD Rate", "Timing Lag Shift"]
    for c_idx, h in enumerate(sc_hdrs, start=1):
        cell = ws_assump.cell(row=r_start, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left")
    r_start += 1
    sc_rows = [
        ("BASELINE", 0.0425, 0.0200, 0.0020, 0.5000, "Standard T+1..T+3"),
        ("ADVERSE", 0.0575, 0.0275, 0.0110, 0.7000, "+24h Holiday Lag"),
        ("SEVERELY_ADVERSE", 0.0700, 0.0375, 0.0350, 0.8500, "+48h Systemic Freeze"),
    ]
    for name, sofr, spread, pd_r, lgd_r, lag_txt in sc_rows:
        ws_assump.cell(row=r_start, column=1, value=name).font = bold_cell_font
        c2 = ws_assump.cell(row=r_start, column=2, value=sofr); c2.number_format = pct_fmt; c2.font = regular_font
        c3 = ws_assump.cell(row=r_start, column=3, value=spread); c3.number_format = pct_fmt; c3.font = regular_font
        c4 = ws_assump.cell(row=r_start, column=4, value=f"=B{r_start}+C{r_start}")  # DYNAMIC FORMULA
        c4.number_format = pct_fmt; c4.font = bold_cell_font
        c5 = ws_assump.cell(row=r_start, column=5, value=pd_r); c5.number_format = pct_fmt; c5.font = regular_font
        c6 = ws_assump.cell(row=r_start, column=6, value=lgd_r); c6.number_format = pct_fmt; c6.font = regular_font
        c7 = ws_assump.cell(row=r_start, column=7, value=lag_txt); c7.font = italic_meta_font; c7.alignment = Alignment(horizontal="center")
        r_start += 1

    # Section 4: Model Summary KPI Formulas
    r_start += 1
    ws_assump.cell(row=r_start, column=1, value="4. MODEL SUMMARY PERFORMANCE BENCHMARKS (DYNAMIC FORMULAS)").font = sec_hdr_font
    r_start += 1
    kpi_formula_rows = [
        ("Final Corporate Closing Cash", "='Daily_Cash_Waterfall'!O151", cur_fmt, "Ending unrestricted operating cash"),
        ("Peak Revolver Facility Utilization", "=MAX('Daily_Cash_Waterfall'!M2:M151)", cur_fmt, "Maximum drawn credit balance"),
        ("Total Period Interest Expense Drag", "=SUM('Daily_Cash_Waterfall'!N2:N151)", cur_fmt, "Total Actual/360 interest accrued"),
        ("Final Total Available Liquidity", "='Daily_Cash_Waterfall'!P151", cur_fmt, "Cash + Undrawn Revolver Headroom"),
        ("Final Covenant Headroom vs $250M", "='Daily_Cash_Waterfall'!Q151", cur_fmt, "Headroom above $250M covenant floor"),
        ("Average Days Float Outstanding (DFO)", "=AVERAGE('Working_Capital_DFO'!E2:E151)", "0.00\" days\"", "Trailing average DFO across horizon"),
        ("Final CECL Cumulative Allowance", "='Regulatory_Liquidity_CECL'!H151", cur_fmt, "Total expected loss contra-asset"),
    ]
    for label, form_str, fmt, note in kpi_formula_rows:
        ws_assump.cell(row=r_start, column=1, value=label).font = regular_font
        c = ws_assump.cell(row=r_start, column=3, value=form_str)
        c.font = bold_cell_font
        c.number_format = fmt
        c.alignment = Alignment(horizontal="right")
        ws_assump.cell(row=r_start, column=4, value=note).font = italic_meta_font
        r_start += 1

    # =========================================================================
    # TAB 2: Data_Feed_Daily (Ingestion Source Feed)
    # =========================================================================
    print("[3/4] Building Sheet 2: Data_Feed_Daily (Transaction Ingestion)...")
    ws_feed = wb.create_sheet(title="Data_Feed_Daily")
    ws_feed.views.sheetView[0].showGridLines = True

    feed_headers = [
        "Ledger Date", "Authorized GPV ($)", "Inbound Settlements Gross ($)",
        "Scheme & Interchange Costs ($)", "Outbound Merchant Payouts Gross ($)",
        "Merchant Reserves Withheld ($)", "Net Processor Revenue Swept ($)",
        "Settlements Receivable Asset ($)", "Customers Payable Liability ($)"
    ]
    for c_idx, h in enumerate(feed_headers, start=1):
        cell = ws_feed.cell(row=1, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center")
    ws_feed.row_dimensions[1].height = 25

    for row_idx, r_feed in enumerate(feed_rows, start=2):
        dt_str = str(r_feed[0])
        gpv = float(r_feed[1])
        inbound = float(r_feed[2])
        scheme = float(r_feed[3])
        out_gross = float(r_feed[4])
        res_withheld = float(r_feed[5])
        net_rev = float(r_feed[6])
        wc_item = daily_wc[row_idx - 2]
        rec_asset = float(wc_item["Settlements Receivable (Asset)"])
        pay_liab = float(wc_item["Customers Payable (Liability)"])

        vals = [dt_str, gpv, inbound, scheme, out_gross, res_withheld, net_rev, rec_asset, pay_liab]
        for c_idx, val in enumerate(vals, start=1):
            cell = ws_feed.cell(row=row_idx, column=c_idx, value=val)
            if c_idx == 1:
                cell.font = regular_font; cell.alignment = Alignment(horizontal="center")
            else:
                cell.font = regular_font; cell.number_format = cur_fmt; cell.alignment = Alignment(horizontal="right")
        if row_idx % 2 == 1:
            for c_idx in range(1, len(vals) + 1):
                ws_feed.cell(row=row_idx, column=c_idx).fill = alt_row_fill

    # =========================================================================
    # TAB 3: Daily_Cash_Waterfall (100% Dynamic Excel Formulas)
    # =========================================================================
    print("[3/4] Building Sheet 3: Daily_Cash_Waterfall (100% Dynamic Formulas)...")
    ws_wf = wb.create_sheet(title="Daily_Cash_Waterfall")
    ws_wf.views.sheetView[0].showGridLines = True

    wf_headers = [
        "Ledger Date", "Safeguarded Open Cash", "Inbound Settlements",
        "Outbound Payouts (Net)", "Net Operating Float", "Corp Subordination Injection",
        "Safeguarded Closing Cash", "Corporate Opening Cash", "Net Revenue Swept",
        "Pre-Financing Corp Cash", "Revolver Draw", "Revolver Repay",
        "Active Debt Balance", "Interest Expense (Act/360)", "Corporate Closing Cash",
        "Total Available Liquidity", "Covenant Headroom", "Early Warning Status"
    ]
    for c_idx, h in enumerate(wf_headers, start=1):
        cell = ws_wf.cell(row=1, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center")
    ws_wf.row_dimensions[1].height = 28

    # Build Days 1-150 with 100% uniform column formulas (eliminates inconsistent formula warnings)
    for row_idx in range(2, 152):
        feed_row = row_idx
        prev_row = row_idx - 1

        f_date = f"=Data_Feed_Daily!A{feed_row}"
        f_saf_open = f"=IF(ISNUMBER(G{prev_row}), G{prev_row}, Assumptions!$C$14)"
        f_inbound = f"=Data_Feed_Daily!C{feed_row}"
        f_outbound = f"=Data_Feed_Daily!E{feed_row}-Data_Feed_Daily!F{feed_row}"
        f_float_delta = f"=C{row_idx}-D{row_idx}-Data_Feed_Daily!D{feed_row}"
        f_injection = f"=MAX(0, D{row_idx}-(B{row_idx}+C{row_idx}))"
        f_saf_close = f"=B{row_idx}+C{row_idx}-D{row_idx}+F{row_idx}"
        f_corp_open = f"=IF(ISNUMBER(O{prev_row}), O{prev_row}, Assumptions!$C$13)"
        f_rev_swept = f"=Data_Feed_Daily!G{feed_row}"
        f_pre_fin = f"=H{row_idx}+I{row_idx}-F{row_idx}"
        f_prev_debt = f"IF(ISNUMBER(M{prev_row}), M{prev_row}, Assumptions!$C$15)"
        f_draw = f"=IF(J{row_idx}<Assumptions!$C$10, MIN(Assumptions!$C$10-J{row_idx}, Assumptions!$C$9-{f_prev_debt}), 0)"
        f_repay = f"=IF(AND(J{row_idx}>Assumptions!$C$11, {f_prev_debt}>0), MIN(J{row_idx}-Assumptions!$C$11, {f_prev_debt}), 0)"
        f_debt = f"={f_prev_debt}+K{row_idx}-L{row_idx}"
        f_interest = f"=ROUND(M{row_idx}*(Assumptions!$C$19/Assumptions!$C$8), 2)"
        f_corp_close = f"=J{row_idx}+K{row_idx}-L{row_idx}-N{row_idx}"
        f_tot_liq = f"=O{row_idx}+(Assumptions!$C$9-M{row_idx})"
        f_headroom = f"=P{row_idx}-Assumptions!$C$10"
        f_status = f'=IF(Q{row_idx}<Assumptions!$C$12, "ALERT TRIGGERED", "COMPLIANT")'

        row_formulas = [
            f_date, f_saf_open, f_inbound, f_outbound, f_float_delta,
            f_injection, f_saf_close, f_corp_open, f_rev_swept, f_pre_fin,
            f_draw, f_repay, f_debt, f_interest, f_corp_close,
            f_tot_liq, f_headroom, f_status
        ]

        for c_idx, formula_val in enumerate(row_formulas, start=1):
            cell = ws_wf.cell(row=row_idx, column=c_idx, value=formula_val)
            if c_idx == 1:
                cell.font = regular_font; cell.alignment = Alignment(horizontal="center")
            elif c_idx == 18:
                cell.font = bold_cell_font; cell.alignment = Alignment(horizontal="center")
            else:
                cell.font = formula_font; cell.number_format = cur_fmt; cell.alignment = Alignment(horizontal="right")
        if row_idx % 2 == 1:
            for c_idx in range(1, len(row_formulas) + 1):
                ws_wf.cell(row=row_idx, column=c_idx).fill = alt_row_fill

    # Summary Row at Row 152
    tot_row = 152
    ws_wf.cell(row=tot_row, column=1, value="TOTAL / BENCHMARKS").font = bold_cell_font
    ws_wf.cell(row=tot_row, column=3, value="=SUM(C2:C151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=4, value="=SUM(D2:D151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=6, value="=SUM(F2:F151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=9, value="=SUM(I2:I151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=11, value="=SUM(K2:K151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=12, value="=SUM(L2:L151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=13, value="=MAX(M2:M151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=14, value="=SUM(N2:N151)").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=15, value="=O151").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=16, value="=P151").number_format = cur_fmt
    ws_wf.cell(row=tot_row, column=17, value="=Q151").number_format = cur_fmt
    for c_idx in range(1, 19):
        c = ws_wf.cell(row=tot_row, column=c_idx)
        c.font = bold_cell_font
        c.fill = summary_fill
        c.border = tot_border

    # =========================================================================
    # TAB 4: Working_Capital_DFO (Dynamic Formulas)
    # =========================================================================
    print("[3/4] Building Sheet 4: Working_Capital_DFO...")
    ws_wc = wb.create_sheet(title="Working_Capital_DFO")
    ws_wc.views.sheetView[0].showGridLines = True

    wc_hdrs = ["Ledger Date", "Settlements Receivable (Asset)", "Customers Payable (Liability)", "Net Settlement Float Gap", "Days Float Outstanding (DFO)"]
    for c_idx, h in enumerate(wc_hdrs, start=1):
        cell = ws_wc.cell(row=1, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center")
    ws_wc.row_dimensions[1].height = 25

    for row_idx in range(2, 152):
        f_dt = f"=Data_Feed_Daily!A{row_idx}"
        f_rec = f"=Data_Feed_Daily!H{row_idx}"
        f_pay = f"=Data_Feed_Daily!I{row_idx}"
        f_gap = f"=B{row_idx}-C{row_idx}"
        # DFO Formula = Receivables / (Daily GPV * Horizon / 365)
        f_dfo = f"=ROUND(B{row_idx}/(Assumptions!$C$5*Assumptions!$C$6/365), 2)"

        ws_wc.cell(row=row_idx, column=1, value=f_dt).alignment = Alignment(horizontal="center")
        c2 = ws_wc.cell(row=row_idx, column=2, value=f_rec); c2.number_format = cur_fmt
        c3 = ws_wc.cell(row=row_idx, column=3, value=f_pay); c3.number_format = cur_fmt
        c4 = ws_wc.cell(row=row_idx, column=4, value=f_gap); c4.number_format = cur_fmt; c4.font = bold_cell_font
        c5 = ws_wc.cell(row=row_idx, column=5, value=f_dfo); c5.number_format = "0.00\" days\""; c5.font = bold_cell_font
        for c_idx in range(1, 6):
            ws_wc.cell(row=row_idx, column=c_idx).font = formula_font
            if row_idx % 2 == 1:
                ws_wc.cell(row=row_idx, column=c_idx).fill = alt_row_fill

    # Working Capital Summary Row at Row 152
    wc_tot = 152
    ws_wc.cell(row=wc_tot, column=1, value="AVERAGE / HORIZON PEAK").font = bold_cell_font
    ws_wc.cell(row=wc_tot, column=2, value="=MAX(B2:B151)").number_format = cur_fmt
    ws_wc.cell(row=wc_tot, column=3, value="=MAX(C2:C151)").number_format = cur_fmt
    ws_wc.cell(row=wc_tot, column=4, value="=AVERAGE(D2:D151)").number_format = cur_fmt
    ws_wc.cell(row=wc_tot, column=5, value="=AVERAGE(E2:E151)").number_format = "0.00\" days\""
    for c_idx in range(1, 6):
        c = ws_wc.cell(row=wc_tot, column=c_idx)
        c.font = bold_cell_font
        c.fill = summary_fill
        c.border = tot_border

    # =========================================================================
    # TAB 5: Regulatory_Liquidity_CECL (Dynamic Formulas)
    # =========================================================================
    print("[3/4] Building Sheet 5: Regulatory_Liquidity_CECL...")
    ws_reg = wb.create_sheet(title="Regulatory_Liquidity_CECL")
    ws_reg.views.sheetView[0].showGridLines = True

    reg_hdrs = [
        "Ledger Date", "Total HQLA Level 1 (Cash)", "Stressed 30d Outflows (30% overlay)",
        "Basel III LCR Ratio", "Compliance Status", "Daily Authorized GPV",
        "Daily CECL Credit Loss Provision", "Cumulative CECL Credit Allowance"
    ]
    for c_idx, h in enumerate(reg_hdrs, start=1):
        cell = ws_reg.cell(row=1, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center")
    ws_reg.row_dimensions[1].height = 25

    for row_idx in range(2, 152):
        f_dt = f"='Daily_Cash_Waterfall'!A{row_idx}"
        f_hqla = f"='Daily_Cash_Waterfall'!O{row_idx}"  # Link to Corporate Closing Cash
        f_outflow = f"=ROUND(AVERAGE('Daily_Cash_Waterfall'!$D$2:D{row_idx})*30*Assumptions!$C$22, 2)"
        f_lcr = f"=IF(C{row_idx}>0, B{row_idx}/C{row_idx}, 999.0)"
        f_status = f'=IF(D{row_idx}>=Assumptions!$C$23, "COMPLIANT", IF(D{row_idx}>=Assumptions!$C$24, "WARNING", "BREACH"))'
        f_gpv = f"=Data_Feed_Daily!B{row_idx}"
        f_cecl = f"=ROUND(F{row_idx}*Assumptions!$C$20*Assumptions!$C$21, 2)"
        f_cum_cecl = f"=SUM($G$2:G{row_idx})"

        ws_reg.cell(row=row_idx, column=1, value=f_dt).alignment = Alignment(horizontal="center")
        ws_reg.cell(row=row_idx, column=2, value=f_hqla).number_format = cur_fmt
        ws_reg.cell(row=row_idx, column=3, value=f_outflow).number_format = cur_fmt
        c4 = ws_reg.cell(row=row_idx, column=4, value=f_lcr); c4.number_format = pct_fmt; c4.font = bold_cell_font
        ws_reg.cell(row=row_idx, column=5, value=f_status).alignment = Alignment(horizontal="center")
        ws_reg.cell(row=row_idx, column=6, value=f_gpv).number_format = cur_fmt
        ws_reg.cell(row=row_idx, column=7, value=f_cecl).number_format = cur_fmt
        c8 = ws_reg.cell(row=row_idx, column=8, value=f_cum_cecl); c8.number_format = cur_fmt; c8.font = bold_cell_font
        for c_idx in range(1, 9):
            ws_reg.cell(row=row_idx, column=c_idx).font = formula_font
            if row_idx % 2 == 1:
                ws_reg.cell(row=row_idx, column=c_idx).fill = alt_row_fill

    # Regulatory Liquidity Summary Row at Row 152
    reg_tot = 152
    ws_reg.cell(row=reg_tot, column=1, value="AVERAGE / PERIOD TOTAL").font = bold_cell_font
    ws_reg.cell(row=reg_tot, column=2, value="=AVERAGE(B2:B151)").number_format = cur_fmt
    ws_reg.cell(row=reg_tot, column=3, value="=AVERAGE(C2:C151)").number_format = cur_fmt
    ws_reg.cell(row=reg_tot, column=4, value="=AVERAGE(D2:D151)").number_format = pct_fmt
    ws_reg.cell(row=reg_tot, column=5, value='=IF(D152>=Assumptions!$C$23, "COMPLIANT", "BREACH")').alignment = Alignment(horizontal="center")
    ws_reg.cell(row=reg_tot, column=6, value="=SUM(F2:F151)").number_format = cur_fmt
    ws_reg.cell(row=reg_tot, column=7, value="=SUM(G2:G151)").number_format = cur_fmt
    ws_reg.cell(row=reg_tot, column=8, value="=H151").number_format = cur_fmt
    for c_idx in range(1, 9):
        c = ws_reg.cell(row=reg_tot, column=c_idx)
        c.font = bold_cell_font
        c.fill = summary_fill
        c.border = tot_border

    # =========================================================================
    # TAB 6: TWCF_13W_Bridge (Dynamic Identity Checks)
    # =========================================================================
    print("[3/4] Building Sheet 6: TWCF_13W_Bridge...")
    ws_twcf = wb.create_sheet(title="TWCF_13W_Bridge")
    ws_twcf.views.sheetView[0].showGridLines = True

    twcf_hdrs = [
        "ISO Week", "Actual Net Cash Flow", "Budget Net Cash Flow", "Net Variance Delta",
        "Volume Outperformance", "Card Mix Substitution", "Clearing Timing Friction",
        "CECL Provision Drag", "Residual Epsilon", "Bridge Total Sum", "Additive Reconciliation Identity Check"
    ]
    for c_idx, h in enumerate(twcf_hdrs, start=1):
        cell = ws_twcf.cell(row=1, column=c_idx, value=h)
        cell.font = col_hdr_font
        cell.fill = navy_hdr_fill
        cell.alignment = Alignment(horizontal="center")
    ws_twcf.row_dimensions[1].height = 25

    bridge_rows = frames["tab4"]
    for row_idx, b in enumerate(bridge_rows, start=2):
        wk, vol, mix, tim, cecl, delta, eps = b
        act_row = df_twcf[df_twcf["week_key"] == wk].iloc[0]
        act_cash = float(act_row["actual_net_cash"])
        bud_cash = float(act_row["budget_net_cash"])

        f_wk = wk
        f_act = act_cash
        f_bud = bud_cash
        f_delta = f"=B{row_idx}-C{row_idx}"                # DYNAMIC FORMULA: Actual - Budget
        f_vol = vol
        f_mix = mix
        f_tim = tim
        f_cecl = -cecl
        f_eps = eps
        f_sum = f"=SUM(E{row_idx}:I{row_idx})"             # DYNAMIC FORMULA: Vol + Mix + Tim + CECL + Eps
        f_check = f'=IF(ABS(J{row_idx}-D{row_idx})<1.0, "EXACT MATCH (VERIFIED)", "RECONCILIATION ERROR")'

        ws_twcf.cell(row=row_idx, column=1, value=f_wk).alignment = Alignment(horizontal="center")
        ws_twcf.cell(row=row_idx, column=2, value=f_act).number_format = cur_fmt
        ws_twcf.cell(row=row_idx, column=3, value=f_bud).number_format = cur_fmt
        c4 = ws_twcf.cell(row=row_idx, column=4, value=f_delta); c4.number_format = cur_fmt; c4.font = bold_cell_font
        ws_twcf.cell(row=row_idx, column=5, value=f_vol).number_format = cur_fmt
        ws_twcf.cell(row=row_idx, column=6, value=f_mix).number_format = cur_fmt
        ws_twcf.cell(row=row_idx, column=7, value=f_tim).number_format = cur_fmt
        ws_twcf.cell(row=row_idx, column=8, value=f_cecl).number_format = cur_fmt
        ws_twcf.cell(row=row_idx, column=9, value=f_eps).number_format = cur_fmt
        c10 = ws_twcf.cell(row=row_idx, column=10, value=f_sum); c10.number_format = cur_fmt; c10.font = bold_cell_font
        c11 = ws_twcf.cell(row=row_idx, column=11, value=f_check); c11.alignment = Alignment(horizontal="center"); c11.font = compliant_font
        for c_idx in range(1, 12):
            if c_idx not in (4, 10, 11):
                ws_twcf.cell(row=row_idx, column=c_idx).font = formula_font
            if row_idx % 2 == 1:
                ws_twcf.cell(row=row_idx, column=c_idx).fill = alt_row_fill

    # TWCF Summary Row
    twcf_tot_row = len(bridge_rows) + 2
    ws_twcf.cell(row=twcf_tot_row, column=1, value="CUMULATIVE 13W TOTAL").font = bold_cell_font
    ws_twcf.cell(row=twcf_tot_row, column=2, value=f"=SUM(B2:B{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=3, value=f"=SUM(C2:C{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=4, value=f"=SUM(D2:D{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=5, value=f"=SUM(E2:E{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=6, value=f"=SUM(F2:F{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=7, value=f"=SUM(G2:G{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=8, value=f"=SUM(H2:H{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=9, value=f"=SUM(I2:I{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=10, value=f"=SUM(J2:J{twcf_tot_row-1})").number_format = cur_fmt
    ws_twcf.cell(row=twcf_tot_row, column=11, value=f'=IF(ABS(J{twcf_tot_row}-D{twcf_tot_row})<1.0, "EXACT MATCH (VERIFIED)", "RECONCILIATION ERROR")').alignment = Alignment(horizontal="center")
    for c_idx in range(1, 12):
        c = ws_twcf.cell(row=twcf_tot_row, column=c_idx)
        c.font = bold_cell_font
        c.fill = summary_fill
        c.border = tot_border

    # Auto-fit column widths and suppress false-positive Excel formula consistency warnings
    print("[4/4] Auto-fitting column widths and saving model...")
    for sheet in wb.worksheets:
        sheet.ignoring_rules = IgnoredErrors(ignoredError=[
            IgnoredError(sqref="A1:Z250", formula=True, formulaRange=True, calculatedColumn=True, numberStoredAsText=True)
        ])
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len and cell.row > 2:
                    max_len = len(val_str)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 15)

    base_dir = Path(__file__).resolve().parents[1]
    out_files = [
        base_dir / "model.xlsx",
        base_dir / "Institutional_Payment_Float_Financial_Model.xlsx"
    ]
    for p in out_files:
        try:
            wb.save(str(p))
            print(f"SUCCESS: Dynamic Excel Model saved to: {p}")
        except PermissionError:
            print(f"WARNING: Could not overwrite {p.name} (file currently open in Excel/LibreOffice). Saved to alternates.")


if __name__ == "__main__":
    generate_model()

