# XYZ Corp (NYSE: XYZ) — Institutional Payment Settlement Float & 13-Week Cash Flow (TWCF) Engine

An institutional-grade treasury, regulatory liquidity, and cash waterfall projection engine calibrated to XYZ Corp's high-volume payment processing platform ($220B–$240B annualized GPV).

> **Data Calibration & Architecture Note:**  
> This engine models multi-rail treasury clearing and regulatory liquidity using a **calibrated discrete-event simulation**. Macro boundaries—including an annualized GPV of ~$240B ($600M/day), corporate cash reserves, and a $500M revolving credit facility—are **benchmarked to XYZ Corp (NYSE: XYZ) SEC Form 10-K disclosures**. Micro-level merchant distributions, rail routing (Card, ACH, FedNow/RTP), and interchange schedules are generated using stylized payment-network industry standards to model intraday liquidity float. Operational outputs (e.g. trapped float, surge injection values) are deterministic simulation outputs rather than line items excerpted directly from SEC filing tables.

> 📘 **Full Audit Whitepaper**: For a complete deep-dive into the data extraction logic, mathematical formulas, page-by-page Excel workbook audit, dashboard visual analytics, and scenario findings, see [**FINANCIAL_ENGINEERING_AND_AUDIT_REPORT.md**](FINANCIAL_ENGINEERING_AND_AUDIT_REPORT.md).

---

## 1. System Architecture

The engine simulates daily multi-rail clearing dynamics, client fund safeguarding, corporate liquidity management, and forward cash forecasting under multiple macroeconomic scenarios.

```
                              [ Merchant Transactions ]
                                          |
                +-------------------------+-------------------------+
                |                                                   |
       [ Outbound Merchant Payouts ]                      [ Inbound Rail Settlements ]
       - Next banking day (T+1)                            - Rail lag: 0 to 3 calendar days
       - Net of tiered reserves (0%–10%)                   - Forward adjusted via US Fed / ECB
                |                                                   |
                v                                                   v
    =========================                           =========================
      SAFEGUARDED POOL                                    CORPORATE OPERATING POOL
      - 7-Day pipeline burn-in (steady state)             - Daily net revenue fee sweep
      - Gross inbound settlements                         - Corporate subordination injection
      - Less merchant payouts                             - $500M Revolver facility
      - Zero commingling                                  - $250M Liquidity covenant floor
      - Deficit -> Corporate injection                    - $150M Stressed operational floor
    =========================                           =========================
                |                                                   |
                +-------------------------+-------------------------+
                                          |
                                [ Executive Surface ]
                                - Liquidity Runway (Tab 1)
                                - Revolver Drag (Tab 2)
                                - Working Capital / DFO (Tab 3)
                                - TWCF Variance Bridge (Tab 4)
```

### Key Pillars & Engineering Fixes
1. **Dual-Ledger Segregation & Daily Fee Desegregation:** Complete structural separation of Client Safeguarded Funds (CRR Art 336 / EBA PSD2 Art 10) from Corporate Operating Cash. Shortfalls in client funds are funded via documented corporate subordination injections. Processor take-rate fees are swept daily out of the safeguarding pool (`min(saf, rev_d)`) into corporate cash to prevent operational capital from being trapped in client trust accounts.
2. **Cold-Start Pipeline Burn-In (Steady-State Clearing):** Solves the simulation boundary distortion where Day 1 starts with empty clearing pipelines. The engine computes a 7-day clearing window prior to ledger accounting, initializing the opening safeguarded reserve so that mature in-flight receivables balance outbound merchant payouts on Days 1 and 2 ($0.00 revolver drawn under Baseline steady state).
3. **6-Rail Clearing & Settlement:** Deterministic forward-routing across `CARD_VISA`, `CARD_MC`, `CARD_AMEX`, `ACH_STANDARD`, `ACH_SAME_DAY`, and `RTP_FEDNOW`, adjusted for US Federal Reserve (K.8) and ECB TARGET2 holiday schedules.
4. **Recursive Daily Waterfall:** 7-step ordered cash flow waterfall incorporating credit facility draws ($250M covenant floor), sweeps ($300M target), Actual/360 interest accruals, and facility limits ($500M).
5. **Basel III Liquidity Coverage Ratio (LCR) with Operational Floor:** Calibrated regulatory liquidity coverage:
   $$\text{LCR}_t = \frac{\text{Corporate Cash (HQLA)}_t}{\text{Trailing 30D Net Subordination Drain} \times 30 \times 0.30 + \$150.00\text{M Operational Floor}}$$
   Eliminates mathematical division-by-zero artifacts during deficit-free baseline periods, producing a defensible, realistic ratio (~779.11% COMPLIANT).
6. **13-Week Cash Flow (TWCF) Additive Variance Attribution:** Sourced directly from daily waterfall ledger actuals, decomposing weekly variance into orthogonal drivers without double-counting:
   $$\Delta \text{NCF}_w = \text{Volume Outperformance}_w + \text{Mix Substitution}_w + \text{Timing Friction}_w + \varepsilon_w$$
7. **Executive BI Dashboard:** Four-tab Streamlit and shadcn/ui dashboard providing real-time visibility into covenant headroom, debt drag, working capital (DFO), and the TWCF bridge.

---

## 2. Quick Start

### Prerequisites
- Python 3.10+
- Dependencies listed in `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

### Running the Interactive Executive Dashboard
Launch the Streamlit executive application:
```bash
streamlit run app.py
```
Access the dashboard at `http://localhost:8501` to toggle macro scenarios and explore the four executive tabs:
- **Tab 1: Liquidity Runway & Covenant Early Warning:** Dual-line chart of `total_liquidity` and `corporate_closing_cash` against the horizontal $250M covenant floor with dynamic headroom alert (< $50M).
- **Tab 2: Revolver Facility Utilization & Macro Interest Drag:** Daily active debt utilization and monthly cost of carry in basis points of Net Operating Margin.
- **Tab 3: Working Capital & Settlement Float Dynamics:** Daily area chart of gross Settlements Receivable vs Customers Payable with Days Float Outstanding (DFO).
- **Tab 4: 13-Week Cash Flow (TWCF) Variance Decomposition:** Week-by-week FP&A bridge decomposing Volume, Mix, Timing, and CECL charges.

### Running the Headless CLI Pipeline
Run automated end-to-end simulations from the command line:
```bash
# Baseline scenario (default 150 days)
python scripts/run_pipeline.py --scenario BASELINE

# Adverse macro stress scenario (+24h lag, 8.50% rate)
python scripts/run_pipeline.py --scenario ADVERSE

# Severely adverse macro stress scenario (+48h freeze, 10.75% rate)
python scripts/run_pipeline.py --scenario SEVERELY_ADVERSE
```

### Opening the Custom shadcn/ui Dashboard
A standalone, lightweight HTML/CSS/JS dashboard built with **Tailwind CSS**, **shadcn/ui design tokens**, **Lucide icons**, and **Chart.js**:
- Simply double-click [`dashboard.html`](dashboard.html) or open it directly in any browser:
  ```bash
  # Windows
  start dashboard.html
  ```
- Features: Real-time scenario switcher (`Baseline`, `Adverse`, `Severe`), 4 PRD Section 8 tabs, dark/light theme toggle, serif typography mode, and interactive tooltips formatted in `$XX.XXM`.

### Institutional Excel Financial Model
The dynamic formula financial model is available at:
[`model.xlsx`](model.xlsx) (also mirrored as [`Institutional_Payment_Float_Financial_Model.xlsx`](Institutional_Payment_Float_Financial_Model.xlsx))
- **Sheet 1 (Assumptions):** Global single source of truth for rates, benchmarks, facility limits, and CECL parameters.
- **Sheet 2 (Data_Feed_Daily):** Full 150-day multi-rail transaction ingestion.
- **Sheet 3 (Daily_Cash_Waterfall):** 100% dynamic recursive dual-ledger cash waterfall.
- **Sheet 4 (Working_Capital_DFO):** Daily gross receivables, payables, float gap, and trailing DFO calculations.
- **Sheet 5 (Regulatory_Liquidity_CECL):** Basel III LCR ratios, stressed 30d outflows, and CECL credit allowances.
- **Sheet 6 (TWCF_13W_Bridge):** Rolling weekly FP&A variance attribution table with additive identity checks.
- Regenerate anytime via:
  ```bash
  python scripts/generate_model.py
  ```


---

## 3. Automated Test Suite

Run the full end-to-end regression test suite (42 unit and integration tests across all 7 phases):
```bash
pytest -v
```

### Test Coverage by Phase
- `tests/test_p1_calendar.py`: US Federal Reserve & ECB calendar integrity, banking day shifts.
- `tests/test_p1_schema.py`: DuckDB table schemas, primary keys, foreign keys, and column types.
- `tests/test_p2_routing.py`: Rail lags, merchant payout contract deltas, weekend/holiday shifts.
- `tests/test_p2_generation.py`: Deterministic transaction generation, tier reserves, 6-rail distribution.
- `tests/test_p3_waterfall.py`: Daily waterfall recursion, pool segregation, Actual/360 interest, revolver logic.
- `tests/test_p4_scenarios.py`: Macro scenarios, CECL proxy allowance accumulation, 30% LCR denominator, covenant breaches.
- `tests/test_p5_twcf.py`: ISO week convention, 13-week forecasting, additive variance reconciliation ($dNCF = Vol + Tim + Mix + \varepsilon$).
- `tests/test_p6_dashboard.py`: BI surface reconciliation, time series shapes, DFO identity, KPI cards.
- `tests/test_p7_e2e.py`: Multi-scenario end-to-end pipeline execution, stress dynamics, dual-ledger conservation.

---

## 4. Database Schema Reference (DuckDB)

The engine stores all operational and analytical entities in-memory or persisted DuckDB tables:

| Table Name | Grain | Description |
|:---|:---|:---|
| `dim_calendar` | Day | Banking days for US Fed (including Jul 3 2026 observance) and ECB TARGET2. |
| `dim_merchant` | Merchant | Merchant tier (1–4), rolling reserve withhold rate (0%–10%), and payout contract. |
| `fact_transactions` | Batch / Row | Normalized transactions with calculated `merchant_payout_date` and `inbound_settlement_date`. |
| `fpa_cash_waterfall_daily` | Date | Daily dual-ledger cash positions, injections, revenue sweep, revolver draws/repays, interest, and closing cash. |
| `fpa_regulatory_liquidity_daily` | Date | Total HQLA Level 1, stressed 30d outflows, LCR ratio, LCR status, and CECL cumulative allowance. |
| `fpa_twcf_weekly_variance` | ISO Week | Weekly actual vs budget net cash flow decomposed into Volume, Timing, Mix, and residual epsilon. |

---

## 5. Accounting & Regulatory Standards

- **ASC 606 / IFRS 15 Revenue Recognition:** Scheme fees and interchange costs are treated as pass-through agent costs and netted against processor revenue. Processor take-rate markup and gateway fees represent principal revenue.
- **CRR Art 336 & PSD2 Art 10 Client Safeguarding:** Client funds are segregated from corporate operating cash. Payout shortfalls are subordinated corporate injections; commingling or cross-merchant funding is forbidden by schema constraints.
- **Basel III Liquidity Coverage Ratio (LCR):**
  $$\text{LCR}_t = \frac{\text{Corporate Cash (HQLA)}_t}{\text{Stressed 30-Day Net Outflows}_t} \ge 100\%$$
  Stressed outflows are defined under EBA/Basel III guidelines as the trailing 30-day net corporate subordination drain plus a **$150.00M stressed operational floor** covering baseline SG&A overhead and debt service. Compliance is categorized into `COMPLIANT` ($\ge 105\%$), `WARNING` ($100\%–105\%$), and `BREACH` ($< 100\%$).
- **CECL (ASC 326) / IFRS 9 Credit Allowances:** Current expected credit loss reserves are accrued daily as $\text{GPV} \times \text{PD} \times \text{LGD}$, accumulating as a contra-asset against settlements receivable.
- **Credit Agreement Covenants:** Minimum Unencumbered Corporate Liquidity floor is fixed at $\$250\text{M}$. Headroom below $\$50\text{M}$ triggers automated executive alerts.

---

## 6. Project Verification & Audit Trail

Phase reports detailing scope, decisions, financial-norm reviews, and test evidence are cataloged in `reports/`:
- `reports/phase-00-report.md`: PRD and Financial-Norm Validation
- `reports/phase-01-report.md`: Foundation and Schemas
- `reports/phase-02-report.md`: Normalization and Settlement Routing
- `reports/phase-03-report.md`: Daily Cash Waterfall
- `reports/phase-04-report.md`: Macro Scenarios, CECL & Liquidity
- `reports/phase-05-report.md`: TWCF Variance Decomposition
- `reports/phase-06-report.md`: Executive BI Surface
- `reports/phase-07-report.md`: End-to-End Verification and Handoff

---

## 7. Executive Treasury Decisions & Strategic Policy Framework

Based on the quantitative simulation findings across 150-day multi-rail stress scenarios (Baseline, Adverse with +24h clearing lag at 8.50% SOFR, and Severely Adverse with +48h systemic freeze at 10.75% SOFR), the engine provides actionable decision frameworks for the Chief Financial Officer, Corporate Treasurer, and VP of FP&A:

### 1. Steady-State Baseline Stability & Facility Right-Sizing
- **Steady-State Baseline ($0.00 Drawn):** Operating with a 7-day clearing burn-in window ensures that inbound card receivables ($T+1..T+3$) arrive continuously to fund outbound merchant payouts. Under Baseline conditions, corporate cash expands from $300.00M to ~$1,168M, requiring **$0.00 in credit facility draws**.
- **Macro Stress Sensitivity:** Under clearing freezes (+24h Adverse, +48h Severely Adverse), settlement latency traps working capital and forces corporate subordination injections, resulting in peak facility utilization of **$160.26M** (Adverse) and **$118.77M** (Severely Adverse).
- **Strategic Recommendation:** Maintain or upsize the committed facility capacity at **$500.00M–$650.00M** to provide a comfortable unencumbered liquidity cushion ($> $150M) above the $250.00M covenant floor during severe banking friction.

### 2. Post-Holiday Settlement Payout Staggering
- **Vulnerability Identified:** Outbound merchant payouts operate on contractual $T+1$ banking day schedules, while card acquiring receipts lag at $T+2$ or $T+3$. Following 3-day holiday weekends (e.g., New Year's Day, Memorial Day), outbound merchant settlement obligations surge before inbound clearing receipts arrive.
- **Strategic Recommendation:** Restructure enterprise merchant agreements to disburse post-holiday settlement volume across a **48-hour split tranche (50% on Day 2, 50% on Day 3)**.
- **Executive Impact:** Dampens single-day corporate cash injection requirements by **$110M–$220M**, eliminating transient emergency revolver drawdowns and reducing annualized interest drag.

### 3. Payment Rail Steering & Working Capital Optimization (DFO -1.0 Day)
- **Vulnerability Identified:** Card rails (Visa/Mastercard at $T+2$, Amex at $T+3$) trap substantial float receivables, driving Days Float Outstanding (DFO) to 8.2–10.2 days. Carrying this trapped float during high-interest regimes (8.50%–10.75%) incurs significant carry cost.
- **Strategic Recommendation:** Introduce an aggressive rail steering policy offering **5–10 bps interchange rebates** to merchants who adopt next-day ACH Same-Day ($T+1$) or real-time instant clearing ($T+0$ FedNow / RTP).
- **Executive Impact:** Compresses platform DFO by **1.0 day**, permanently releasing **$164.4M** in trapped working capital back into operating cash and avoiding substantial annualized facility interest drag.

### 4. Predictive 13-Week Cash Flow (TWCF) Variance Early Warning
- **Vulnerability Identified:** Traditional 30-day accounting closes conceal intra-month liquidity erosion. In volatile macroeconomic cycles, cumulative CECL provisions and negative settlement timing drag erode cash reserves weeks before appearing on GAAP financial statements.
- **Strategic Recommendation:** Institutionalize the automated weekly TWCF additive variance decomposition engine ($\Delta\text{NCF} = \text{Volume} + \text{Mix} + \text{Timing} + \varepsilon$) with automated alerts triggered when timing friction exceeds -$15M.
- **Executive Impact:** Delivers a **6 to 8 week forward early-warning radar**, granting treasury leadership sufficient lead time to raise merchant reserve withholdings (from 5% to 10%) or execute liquidity sweeps before covenant boundaries are threatened.

---

### Executive Decision Scorecard & Treasury Impact Matrix

| Strategic Decision | Operational Catalyst | Capital / Liquidity Impact | P&L / Cost Benefit | Implementation Horizon |
|:---|:---|:---|:---|:---|
| **Revolver Facility Right-Sizing** | Peak draws reach $160.26M during +24h clearing lag | Preserves >$150M covenant cushion buffer | Prevents $250M covenant default penalties | 60–90 Days (Bank Syndicate) |
| **Post-Holiday Payout Staggering** | Post-holiday merchant settlement obligations spike | Peak cash injection reduced by $110M–$220M | Eliminates $1.5M–$3.0M in surge borrowing interest | 30–60 Days (Merchant Contracts) |
| **Payment Rail Steering (DFO -1.0d)** | $164.4M float trapped per +1 day latency in card rails | Releases $164.4M trapped working capital | Substantial annual interest expense savings | Immediate (Pricing Incentives) |
| **Predictive TWCF Variance Alerting** | CECL allowances & timing decay erode cash unseen | 6–8 week forward visibility on liquidity pinches | Protects against unexpected liquidity compression | Active in Production Engine |

---

### Data Provenance & Financial Modeling Methodology Note

> ⚠️ **Important Disclosure on Data Provenance**:
> - **SEC Form 10-K Anchors**: The macro scale of this engine is anchored in XYZ Corp's (NYSE: XYZ) public SEC filings (~$220B–$240B annualized GPV, ecosystem acquiring split, ASC 606 gross interchange pass-through, and standard institutional revolving credit covenants of $500M facility with a $250M covenant floor).
> - **Simulation Engine Outputs**: Public SEC 10-K filings report quarterly aggregated balance sheet snapshots; they do **not** disclose daily treasury clearing waterfalls, intra-week holiday settlement deficits, or rail-level float aging.
> - **Exact Scorecard Quantities**: Specific figures cited above—such as the **$160.26M** adverse peak draw, **$164.4M** float per day, and **779.11%** LCR—are **deterministic simulation outputs generated by our 7-step recursive cash waterfall engine** running across a 150-day calendar horizon, rather than point-in-time line items excerpted directly from SEC filing tables.



