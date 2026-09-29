"""Streamlit Executive BI Surface: Institutional Settlement Float & TWCF Engine.

PRD Section 8 implementation with executive financial styling:
- Compact, proportional chart heights (320px–360px).
- Rich interactive tooltips with explicit dollar signs and millions formatting ($XX.XXM).
- Professional financial styling with KPI metric cards, status badges, and benchmark reference lines.
- Native Plotly charts including time-series dual-line, bar, area, and FP&A Waterfall bridge.

Usage:
    streamlit run app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.database import initialize_database
from src.transactions import seed_merchants, generate_synthetic_transactions
from src.waterfall import execute_daily_waterfall_engine
from src.twcf import weekly_variance
from src.dashboard import build_dashboard_frames, HEADROOM_ALERT, COVENANT_FLOOR, REVOLVER_LIMIT
from src.scenarios import MACRO_PARAMS, PD_LGD, LAG_SHIFT_DAYS, borrowing_rate

SCENARIOS = ("BASELINE", "ADVERSE", "SEVERELY_ADVERSE")


@st.cache_resource(show_spinner="Simulating institutional settlement engine (150 days)...")
def engine(scenario):
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
    execute_daily_waterfall_engine(con, macro_scenario=scenario)
    weekly_variance(con)
    return con


# ---------------------------------------------------------------------------
# Page Configuration & Executive Styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Block, Inc. (NYSE: SQ) | Settlement Float & TWCF Treasury Engine",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Custom Executive CSS for KPI cards, status banners, and preserving Streamlit icons
st.markdown("""
<style>
    /* Explicitly protect all Streamlit Material icons from being overridden */
    [data-testid*="stIcon"],
    [data-testid*="stIconMaterial"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons,
    [class*="material-symbols"],
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="collapsedControl"] span {
        font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons" !important;
    }
    
    .status-banner {
        padding: 13px 18px;
        border-radius: 8px;
        margin-bottom: 16px;
        font-size: 0.95rem;
        line-height: 1.5;
    }

    .status-compliant {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        color: #166534;
    }
    .status-alert {
        background-color: #fef2f2;
        border: 1px solid #fecaca;
        color: #991b1b;
    }

    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .metric-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .metric-value {
        font-size: 1.55rem;
        font-weight: 700;
        color: #0f172a;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-feature-settings: "tnum" 1;
    }
    .badge-compliant {
        display: inline-block;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 700;
        border-radius: 12px;
        background-color: #dcfce7;
        color: #15803d;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .badge-warning {
        display: inline-block;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 700;
        border-radius: 12px;
        background-color: #fef3c7;
        color: #b45309;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .badge-breach {
        display: inline-block;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 700;
        border-radius: 12px;
        background-color: #fee2e2;
        color: #b91c1c;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar: Scenario Selection & Macro Environment
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏦 Macro Parameters")
    scenario = st.selectbox("Active Macro Scenario", SCENARIOS, index=0)
    params = MACRO_PARAMS[scenario]
    pd_lgd = PD_LGD[scenario]
    
    st.markdown("---")
    rate_val = float(borrowing_rate(scenario))
    st.markdown(f"**Borrowing Rate:** `{rate_val:.2%}`")
    st.caption(f"• Base SOFR: {float(params['sofr']):.2%}\n• Credit Spread: {float(params['spread']):.2%}")
    
    st.markdown(f"**CECL Credit Risk:**")
    st.caption(f"• Probability of Default: {float(pd_lgd['pd']):.2%}\n• Loss Given Default: {float(pd_lgd['lgd']):.0%}")
    
    st.markdown(f"**Clearing Friction:**")
    lag_txt = "Standard T+1..T+3" if scenario == "BASELINE" else ("+24h Holiday Lag" if scenario == "ADVERSE" else "+48h Systemic Freeze")
    st.caption(f"• Rail Timing Shift: {lag_txt}")
    
    st.markdown("---")
    st.markdown(f"**Facility Benchmarks:**")
    st.caption(f"• Revolver Capacity: **${REVOLVER_LIMIT/1e6:,.0f}M**\n• Covenant Floor: **${COVENANT_FLOOR/1e6:,.0f}M**\n• Early Warning Trigger: **< ${HEADROOM_ALERT/1e6:,.0f}M**")


# ---------------------------------------------------------------------------
# Header & Data Ingestion
# ---------------------------------------------------------------------------
st.title("Block, Inc. (NYSE: SQ) — Settlement Float & 13W Cash Flow")
st.caption(f"150-Day Institutional Treasury Engine | Dual-Ledger Cash Waterfall | Macro Scenario: **{scenario}** | Benchmark: SEC Form 10-K Calibration")


con = engine(scenario)
frames = build_dashboard_frames(con, scenario)

tab1, tab2, tab3, tab4 = st.tabs([
    "1. Liquidity Runway & Covenants",
    "2. Revolver Facility & Drag",
    "3. Working Capital & Float (DFO)",
    "4. 13-Week Cash Flow Bridge"
])


# ---------------------------------------------------------------------------
# TAB 1: Liquidity Runway & Covenant Early Warning
# ---------------------------------------------------------------------------
with tab1:
    k = frames["tab1"]
    
    # Early warning status banner rendered via HTML to preserve exact currency symbols
    if k["alert"]:
        st.markdown(f"""
        <div class="status-banner status-alert">
            <strong>⚠️ COVENANT HEADROOM ALERT TRIGGERED</strong>: Current headroom of 
            <strong>${k['covenant_headroom']/1e6:,.2f}M</strong> has breached the policy threshold of 
            <strong>&lt; ${HEADROOM_ALERT/1e6:,.2f}M</strong> against the <strong>${COVENANT_FLOOR/1e6:,.2f}M</strong> covenant floor.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="status-banner status-compliant">
            <strong>✅ COVENANT COMPLIANT</strong>: Headroom stands at 
            <strong>${k['covenant_headroom']/1e6:,.2f}M</strong> 
            (Minimum Safety Buffer: ${HEADROOM_ALERT/1e6:,.2f}M above ${COVENANT_FLOOR/1e6:,.2f}M floor).
        </div>
        """, unsafe_allow_html=True)

    # 3 Key Metric KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Liquidity Cushion</div>
            <div class="metric-value">${k['cushion']/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Cash + Undrawn - Floor</span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Corporate Cash</div>
            <div class="metric-value">${k['corporate_closing_cash']/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Closing Unrestricted Cash</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        rw_txt = f"{k['runway_days']:.2f} Days" if k["runway_days"] else "N/A"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Policy Runway</div>
            <div class="metric-value">{rw_txt}</div>
            <span style="font-size: 0.78rem; color: #64748b;">Total Liquidity / Daily Payout</span>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        badge_cls = "badge-compliant" if k["lcr_status"] == "COMPLIANT" else ("badge-warning" if k["lcr_status"] == "WARNING" else "badge-breach")
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Basel III LCR</div>
            <div class="metric-value">{k['lcr_ratio']:.2%}</div>
            <span class="{badge_cls}">{k['lcr_status']}</span>
        </div>
        """, unsafe_allow_html=True)

    # Primary Visual: Dual-Line Chart with $250M Covenant Floor
    df_series = pd.DataFrame(k["series"])
    df_series["tot_m"] = df_series["total_liquidity"] / 1e6
    df_series["corp_m"] = df_series["corporate_closing_cash"] / 1e6
    df_series["floor_m"] = df_series["covenant_floor"] / 1e6

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=df_series["date"], y=df_series["tot_m"],
        mode="lines", name="Total Available Liquidity",
        line=dict(color="#2563eb", width=2.5),
        hovertemplate="<b>Date</b>: %{x}<br><b>Total Liquidity</b>: $%{y:,.2f}M<extra></extra>"
    ))
    fig1.add_trace(go.Scatter(
        x=df_series["date"], y=df_series["corp_m"],
        mode="lines", name="Corporate Closing Cash",
        line=dict(color="#0d9488", width=2),
        hovertemplate="<b>Date</b>: %{x}<br><b>Corporate Cash</b>: $%{y:,.2f}M<extra></extra>"
    ))
    fig1.add_trace(go.Scatter(
        x=df_series["date"], y=df_series["floor_m"],
        mode="lines", name="Covenant Floor ($250M)",
        line=dict(color="#dc2626", width=2, dash="dash"),
        hovertemplate="<b>Covenant Floor</b>: $%{y:,.2f}M<extra></extra>"
    ))
    fig1.update_layout(
        title="<b>Daily Liquidity Trajectory vs $250M Credit Covenant Floor</b>",
        title_font_size=14,
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
        height=340,
        margin=dict(l=40, r=20, t=45, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="Liquidity ($ Millions)", tickprefix="$", ticksuffix="M", gridcolor="#f1f5f9"),
        xaxis=dict(gridcolor="#f1f5f9"),
        hovermode="x unified",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff"
    )
    st.plotly_chart(fig1, width="stretch")

    # Clear Metric Definition Note
    st.info("""
    💡 **Understanding Liquidity Runway & Covenant Early Warning**:
    * **Total Available Liquidity**: Total deployable treasury resources (Corporate Cash + Undrawn Revolver).
    * **Liquidity Cushion**: Net safety margin above credit covenant (Total Liquidity minus \\$250.00M floor).
    * **Corporate Cash**: Operating cash owned by the company, strictly segregated from safeguarded client funds.
    * **Basel III LCR**: High-Quality Liquid Assets vs 30-day net outflows (greater than or equal to 100% indicates full statutory compliance).
    * **Covenant Headroom Early Warning**: Alerts if corporate cash or cushion approaches the **\\$250.00M** minimum floor, triggering proactive facility actions before technical default.
    """)



# ---------------------------------------------------------------------------
# TAB 2: Revolver Facility Utilization & Macro Interest Drag
# ---------------------------------------------------------------------------
with tab2:
    t2 = frames["tab2"]
    
    col1, col2, col3 = st.columns(3)
    latest_debt = t2["daily"][-1][1] if t2["daily"] else 0.0
    total_interest = sum(i for _, _, i in t2["daily"])
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Active Revolver Debt</div>
            <div class="metric-value">${latest_debt/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Facility Limit: ${REVOLVER_LIMIT/1e6:,.0f}M</span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Effective Borrowing Cost</div>
            <div class="metric-value">{t2['rate']:.2%}</div>
            <span style="font-size: 0.78rem; color: #64748b;">Actual/360 Money Market</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Period Interest Drag</div>
            <div class="metric-value">${total_interest/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Cumulative Expense</span>
        </div>
        """, unsafe_allow_html=True)

    # Primary Visual: Daily Revolver Debt Balance Area Chart (eliminates bar crowding)
    df_debt = pd.DataFrame(t2["daily"], columns=["date", "debt", "interest"])
    df_debt["debt_m"] = df_debt["debt"] / 1e6
    df_debt["int_k"] = df_debt["interest"] / 1e3

    fig2a = go.Figure()
    fig2a.add_trace(go.Scatter(
        x=df_debt["date"], y=df_debt["debt_m"],
        mode="lines", fill="tozeroy",
        name="Active Revolver Debt",
        line=dict(color="#0284c7", width=2.2),
        fillcolor="rgba(2, 132, 199, 0.18)",
        hovertemplate="<b>Date</b>: %{x}<br><b>Active Debt Balance</b>: $%{y:,.2f}M<br><b>Facility Capacity</b>: $500.00M<extra></extra>"
    ))
    fig2a.add_hline(
        y=REVOLVER_LIMIT/1e6, line_dash="dot", line_color="#ef4444",
        annotation_text=f"Max Facility Capacity ${REVOLVER_LIMIT/1e6:,.0f}M",
        annotation_position="top right"
    )
    fig2a.update_layout(
        title="<b>Daily Revolver Facility Utilization ($ Millions) — Area Trajectory</b>",
        title_font_size=14,
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
        height=320,
        margin=dict(l=40, r=20, t=45, b=30),
        yaxis=dict(title="Drawn Debt ($ Millions)", tickprefix="$", ticksuffix="M", gridcolor="#f1f5f9"),
        xaxis=dict(gridcolor="#f1f5f9"),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff"
    )
    st.plotly_chart(fig2a, width="stretch")

    # Clear Scenario Dynamics Note explaining why Debt is $0 in Baseline vs Stress
    st.info("""
    💡 **Understanding Facility Utilization & Scenario Dynamics**:
    * **Steady-State Baseline Stability**: With a 7-day clearing burn-in cycle, in-flight card receipts arrive on Day 2 in steady state, maintaining corporate cash above the **\\$250.00M** covenant floor without triggering credit facility draws (**\\$0.00 drawn** under Baseline).
    * **Macro Stress Sensitivity**: Under **Adverse (+24h lag)** and **Severely Adverse (+48h systemic freeze)**, extended clearing latency causes merchant payouts to temporarily outpace inbound receipts, activating facility borrowing to protect covenant liquidity buffers.
    """)

    # Monthly Cost of Carry Waterfall in bps of Net Operating Margin
    st.markdown("#### Monthly Margin Drag: Revolver Carrying Cost")
    df_carry = pd.DataFrame(t2["monthly_carry_bps"], columns=["month", "carry_bps"])
    
    col_c1, col_c2 = st.columns([3, 2])
    with col_c1:
        fig2b = go.Figure()
        fig2b.add_trace(go.Bar(
            x=df_carry["month"], y=df_carry["carry_bps"],
            marker_color="#f59e0b",
            hovertemplate="<b>Month</b>: %{x}<br><b>Erosion</b>: %{y:.2f} bps of margin<extra></extra>"
        ))
        fig2b.update_layout(
            title="<b>Net Operating Margin Erosion (Basis Points)</b>",
            title_font_size=13,
            font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
            height=260,
            margin=dict(l=40, r=20, t=40, b=30),
            yaxis=dict(title="Margin Drag (bps)", ticksuffix=" bps", gridcolor="#f1f5f9"),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff"
        )
        st.plotly_chart(fig2b, width="stretch")

    with col_c2:
        st.dataframe(
            df_carry.rename(columns={"month": "Projection Month", "carry_bps": "Margin Erosion (bps)"}),
            height=260,
            width="stretch"
        )


# ---------------------------------------------------------------------------
# TAB 3: Working Capital & Settlement Float Dynamics
# ---------------------------------------------------------------------------
with tab3:
    k3 = frames["tab3"]
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Days Float Outstanding</div>
            <div class="metric-value">{k3['dfo']:.2f} Days</div>
            <span style="font-size: 0.78rem; color: #64748b;">Receivables / (GPV / 365)</span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Settlements Receivable</div>
            <div class="metric-value">${k3['receivables']/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Asset (Unsettled Inbound)</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Customers Payable</div>
            <div class="metric-value">${k3['payables']/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Liability (Pending Payouts)</span>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        net_float = (k3['receivables'] - k3['payables'])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Net Settlement Float</div>
            <div class="metric-value">${net_float/1e6:,.2f}M</div>
            <span style="font-size: 0.78rem; color: #64748b;">Receivable vs Payable Gap</span>
        </div>
        """, unsafe_allow_html=True)

    # Primary Visual: Daily Working Capital Area Chart
    df_wc = pd.DataFrame(k3["daily"])
    df_wc["rec_m"] = df_wc["Settlements Receivable (Asset)"] / 1e6
    df_wc["pay_m"] = df_wc["Customers Payable (Liability)"] / 1e6

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=df_wc["date"], y=df_wc["rec_m"],
        mode="lines", fill="tozeroy",
        name="Gross Settlements Receivable (Asset)",
        line=dict(color="#0284c7", width=2),
        fillcolor="rgba(2, 132, 199, 0.18)",
        hovertemplate="<b>Date</b>: %{x}<br><b>Receivables</b>: $%{y:,.2f}M<extra></extra>"
    ))
    fig3.add_trace(go.Scatter(
        x=df_wc["date"], y=df_wc["pay_m"],
        mode="lines", fill="tozeroy",
        name="Gross Customers Payable (Liability)",
        line=dict(color="#d97706", width=2),
        fillcolor="rgba(217, 119, 6, 0.18)",
        hovertemplate="<b>Date</b>: %{x}<br><b>Payables</b>: $%{y:,.2f}M<extra></extra>"
    ))
    fig3.update_layout(
        title="<b>Daily Working Capital: Settlements Receivable (Asset) vs Customers Payable (Liability)</b>",
        title_font_size=14,
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
        height=340,
        margin=dict(l=40, r=20, t=45, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="Working Capital ($ Millions)", tickprefix="$", ticksuffix="M", gridcolor="#f1f5f9"),
        xaxis=dict(gridcolor="#f1f5f9"),
        hovermode="x unified",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff"
    )
    st.plotly_chart(fig3, width="stretch")
    st.info("""
    💡 **Understanding Working Capital & Settlement Float Dynamics**:
    * **Days Float Outstanding (DFO)**: DFO = Gross Settlements Receivable / (Annualized GPV / 365). Measures the timing lag in calendar days between processing merchant payments and collecting cleared funds from acquiring networks.
    * **Gross Settlements Receivable (Asset)**: Cleared customer card authorizations currently in-transit across card schemes (T+2/T+3) not yet deposited in corporate settlement accounts.
    * **Gross Customers Payable (Liability)**: Merchant transaction volumes awaiting contractual batched settlement payout.
    * **Net Settlement Float**: Receivables minus Payables. A positive gap indicates working capital funding absorbed by the treasury; a negative gap indicates platform float benefits.
    """)


# ---------------------------------------------------------------------------
# TAB 4: 13-Week Cash Flow (TWCF) Variance Decomposition
# ---------------------------------------------------------------------------
with tab4:
    t4 = frames["tab4"]
    
    df_bridge = pd.DataFrame([
        {
            "week": r[0],
            "vol_m": r[1] / 1e6,
            "mix_m": r[2] / 1e6,
            "tim_m": r[3] / 1e6,
            "cecl_m": -r[4] / 1e6,
            "net_m": (r[1] + r[2] + r[3] - r[4]) / 1e6,
            "raw_vol": r[1],
            "raw_mix": r[2],
            "raw_tim": r[3],
            "raw_cecl": r[4],
            "raw_eps": r[6]
        }
        for r in t4
    ])

    week_options = ["Cumulative Horizon (All Weeks)"] + list(df_bridge["week"])
    selected_view = st.selectbox("Select Variance Period", week_options, index=0)

    # Isolate data for Waterfall
    if selected_view == "Cumulative Horizon (All Weeks)":
        v_vol = df_bridge["vol_m"].sum()
        v_mix = df_bridge["mix_m"].sum()
        v_tim = df_bridge["tim_m"].sum()
        v_cecl = df_bridge["cecl_m"].sum()
        v_net = v_vol + v_mix + v_tim + v_cecl
        title_txt = "Cumulative FP&A Variance Waterfall ($ Millions)"
    else:
        row = df_bridge[df_bridge["week"] == selected_view].iloc[0]
        v_vol = row["vol_m"]
        v_mix = row["mix_m"]
        v_tim = row["tim_m"]
        v_cecl = row["cecl_m"]
        v_net = row["net_m"]
        title_txt = f"Weekly Variance Bridge for {selected_view} ($ Millions)"

    # Primary Visual: Plotly FP&A Bridge / Waterfall Chart
    fig4 = go.Figure(go.Waterfall(
        name="FP&A Bridge",
        orientation="v",
        measure=["relative", "relative", "relative", "relative", "total"],
        x=["Volume Variance", "Card Mix Shift", "Timing Friction", "CECL Credit Charge", "Net Cash Variance"],
        textposition="outside",
        text=[f"${v_vol:+,.2f}M", f"${v_mix:+,.2f}M", f"${v_tim:+,.2f}M", f"${v_cecl:+,.2f}M", f"${v_net:+,.2f}M"],
        y=[v_vol, v_mix, v_tim, v_cecl, v_net],
        connector={"line": {"color": "#94a3b8", "width": 1.5, "dash": "dot"}},
        decreasing={"marker": {"color": "#ef4444"}},
        increasing={"marker": {"color": "#10b981"}},
        totals={"marker": {"color": "#3b82f6"}}
    ))
    fig4.update_layout(
        title=f"<b>{title_txt}</b>",
        title_font_size=14,
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
        height=340,
        margin=dict(l=40, r=20, t=45, b=30),
        yaxis=dict(title="Contribution ($ Millions)", tickprefix="$", ticksuffix="M", gridcolor="#f1f5f9"),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff"
    )
    st.plotly_chart(fig4, width="stretch")

    # Detailed Weekly Breakdown Table
    st.markdown("#### Weekly FP&A Variance Audit Table")
    df_table_display = pd.DataFrame([
        {
            "Week": r["week"],
            "Volume Variance": f"${r['raw_vol']/1e6:+,.2f}M",
            "Mix Variance": f"${r['raw_mix']/1e6:+,.2f}M",
            "Timing Variance": f"${r['raw_tim']/1e6:+,.2f}M",
            "CECL Provision": f"${r['raw_cecl']/1e6:,.2f}M",
            "Residual (eps)": f"${r['raw_eps']:,.2f}"
        }
        for _, r in df_bridge.iterrows()
    ])
    st.dataframe(df_table_display, width="stretch")
    st.info("""
    💡 **Understanding the 13-Week Cash Flow Bridge (TWCF)**:
    * **Additive Identity**: Actual Net Cash − Budget Net Cash = Volume Variance + Card Mix Shift + Timing Friction + CECL Credit Provision + Residual (ε).
    * **Volume Variance**: Cash impact from gross transaction volume deviations (GPV) versus initial budget projections.
    * **Card Mix Shift**: Liquidity variance caused by mix shifts between interchange rates (Credit vs Debit vs ACH).
    * **Timing Friction**: Liquidity shifts caused by bank holidays, weekend settlement clustering, and acquirer clearing delays.
    * **CECL Credit Drag**: Current Expected Credit Loss provisions reflecting merchant default risk, chargeback exposure, and macroeconomic probability of default (PD × LGD).
    """)

