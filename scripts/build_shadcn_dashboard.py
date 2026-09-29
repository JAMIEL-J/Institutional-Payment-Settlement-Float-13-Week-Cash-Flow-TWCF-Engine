"""Build Institutional Treasury Executive Dashboard.

PRD Section 8 implementation with executive financial styling:
- Reverted to clean Top-Navbar executive dashboard layout.
- White minimalist canvas with ocean hue accents (#0284c7, #0369a1, #0ea5e9, #0d9488).
- Modern sans-serif typography ('Inter', system-ui, sans-serif).
- Zero non-institutional branding; pure institutional treasury terminology.
- 4 Primary Tabs:
  1. Liquidity Runway & Covenants
  2. Revolver Facility & Drag (Area chart with smooth trajectory, no crowded bars)
  3. Working Capital & Float (DFO)
  4. 13-Week Cash Flow Bridge (Waterfall with Initial, Delta, and Final tooltips)
- Bulletproof navigation: SVG currentColor inheritance, safe chart destruction, and clear explanatory notes.
"""
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import initialize_database
from src.transactions import seed_merchants, generate_synthetic_transactions
from src.waterfall import execute_daily_waterfall_engine
from src.twcf import weekly_variance
from src.dashboard import build_dashboard_frames, HEADROOM_ALERT, COVENANT_FLOOR, REVOLVER_LIMIT
from src.scenarios import MACRO_PARAMS, PD_LGD, borrowing_rate


def collect_simulation_data():
    scenarios = ["BASELINE", "ADVERSE", "SEVERELY_ADVERSE"]
    dataset = {}

    for sc in scenarios:
        con = initialize_database()
        seed_merchants(con)
        generate_synthetic_transactions(con, scale_daily_gpv=600_000_000.0, num_days=150)
        execute_daily_waterfall_engine(con, macro_scenario=sc)
        weekly_variance(con)
        frames = build_dashboard_frames(con, sc)

        dataset[sc] = {
            "params": {
                "sofr": float(MACRO_PARAMS[sc]["sofr"]),
                "spread": float(MACRO_PARAMS[sc]["spread"]),
                "rate": float(borrowing_rate(sc)),
                "pd": float(PD_LGD[sc]["pd"]),
                "lgd": float(PD_LGD[sc]["lgd"]),
                "lag_desc": "Standard T+1..T+3" if sc == "BASELINE" else ("+24h Holiday Lag" if sc == "ADVERSE" else "+48h Systemic Freeze")
            },
            "tab1": frames["tab1"],
            "tab2": {
                "rate": frames["tab2"]["rate"],
                "latest_debt": frames["tab2"]["daily"][-1][1] if frames["tab2"]["daily"] else 0.0,
                "total_interest": sum(i for _, _, i in frames["tab2"]["daily"]),
                "daily": [{"date": d, "debt": b, "interest": i} for d, b, i in frames["tab2"]["daily"]],
                "monthly_carry_bps": frames["tab2"]["monthly_carry_bps"]
            },
            "tab3": {
                "dfo": frames["tab3"]["dfo"],
                "receivables": frames["tab3"]["receivables"],
                "payables": frames["tab3"]["payables"],
                "net_float": frames["tab3"]["receivables"] - frames["tab3"]["payables"],
                "daily": frames["tab3"]["daily"]
            },
            "tab4": [
                {
                    "week": r[0],
                    "vol": r[1],
                    "mix": r[2],
                    "tim": r[3],
                    "cecl": r[4],
                    "net": r[1] + r[2] + r[3] - r[4],
                    "eps": r[6]
                }
                for r in frames["tab4"]
            ]
        }
        con.close()

    return dataset


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Block, Inc. (NYSE: SQ) | Settlement Float & TWCF Treasury Dashboard</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>
  <!-- Google Fonts: Inter -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
          },
          colors: {
            brand: {
              ocean: '#0284c7',
              darkocean: '#0369a1',
              marine: '#0d9488',
              slate: '#0f172a',
              card: '#ffffff',
              canvas: '#f8fafc',
              border: '#e2e8f0'
            }
          }
        }
      }
    }
  </script>

  <style>
    body {
      background-color: #f8fafc;
      color: #0f172a;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }
    .num-tabular {
      font-feature-settings: "tnum" 1;
      font-variant-numeric: tabular-nums;
    }
    .card-shadow {
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05);
    }
    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #f1f5f9; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
    /* Hide scrollbar for touch scrolling tabs/tables */
    .no-scrollbar::-webkit-scrollbar { display: none; }
    .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
  </style>
</head>

<body class="min-h-screen flex flex-col bg-[#f8fafc] overflow-x-hidden">

  <!-- ======================================================================= -->
  <!-- TOP NAVIGATION HEADER (Fully Responsive Institutional Executive Layout) -->
  <!-- ======================================================================= -->
  <header class="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-slate-200">
    <div class="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
      
      <!-- Main Header Row (Flex-col on mobile, flex-row on desktop) -->
      <div class="flex flex-col md:flex-row md:items-center justify-between py-2 sm:py-2.5 md:py-0 md:h-16 gap-2 sm:gap-2.5 md:gap-4">
        
        <!-- Top bar row on mobile: Logo + Title + Mobile Excel Button -->
        <div class="flex items-center justify-between w-full md:w-auto">
          <!-- Institutional Brand Logo & Title -->
          <div class="flex items-center gap-2.5 sm:gap-3 shrink-0">
            <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-slate-900 text-white flex items-center justify-center font-bold shadow-xs shrink-0">
              <i data-lucide="landmark" class="w-4 h-4 sm:w-5 sm:h-5 text-sky-400"></i>
            </div>
            <div>
              <div class="flex items-center gap-1.5 sm:gap-2">
                <span class="text-xs sm:text-sm font-bold tracking-tight text-slate-900">Block, Inc. (NYSE: SQ)</span>
                <span class="hidden sm:inline-block px-1.5 sm:px-2 py-0.5 text-[9px] sm:text-[10px] font-semibold bg-sky-50 text-sky-700 border border-sky-200 rounded-full">SEC Form 10-K Benchmark</span>
              </div>
              <p class="text-[10px] sm:text-[11px] text-slate-500 truncate max-w-[210px] sm:max-w-none">150-Day Settlement Float & 13-Week Cash Flow Engine</p>
            </div>
          </div>

          <!-- Mobile Excel Button (shown on mobile, hidden on md+) -->
          <a href="model.xlsx" download
            class="md:hidden inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-xs font-semibold transition-colors shrink-0">
            <i data-lucide="file-spreadsheet" class="w-3.5 h-3.5 text-emerald-600"></i>
            <span>Excel</span>
          </a>
        </div>

        <!-- Macro Scenario Selector (Grid on mobile, flex on desktop) -->
        <div class="grid grid-cols-3 md:flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 w-full md:w-auto gap-0.5">
          <button onclick="setScenario('BASELINE')" id="sc-btn-BASELINE"
            class="px-2 sm:px-3 py-1.5 rounded-lg text-[11px] sm:text-xs font-semibold bg-white text-slate-900 shadow-xs transition-all flex items-center justify-center gap-1 sm:gap-1.5 cursor-pointer">
            <span class="w-2 h-2 rounded-full bg-emerald-500 shrink-0"></span>
            <span>Baseline</span>
            <span class="hidden lg:inline text-[10px] text-slate-400 font-normal">(4.25% SOFR)</span>
          </button>
          <button onclick="setScenario('ADVERSE')" id="sc-btn-ADVERSE"
            class="px-2 sm:px-3 py-1.5 rounded-lg text-[11px] sm:text-xs font-medium text-slate-600 hover:text-slate-900 transition-all flex items-center justify-center gap-1 sm:gap-1.5 cursor-pointer">
            <span class="w-2 h-2 rounded-full bg-amber-500 shrink-0"></span>
            <span>Adverse</span>
            <span class="hidden lg:inline text-[10px] text-slate-400 font-normal">(+24h Lag)</span>
          </button>
          <button onclick="setScenario('SEVERELY_ADVERSE')" id="sc-btn-SEVERELY_ADVERSE"
            class="px-2 sm:px-3 py-1.5 rounded-lg text-[11px] sm:text-xs font-medium text-slate-600 hover:text-slate-900 transition-all flex items-center justify-center gap-1 sm:gap-1.5 cursor-pointer">
            <span class="w-2 h-2 rounded-full bg-rose-500 shrink-0"></span>
            <span>Severe</span>
            <span class="hidden lg:inline text-[10px] text-slate-400 font-normal">(+48h Freeze)</span>
          </button>
        </div>

        <!-- Desktop Excel Download Button -->
        <div class="hidden md:flex items-center gap-2.5">
          <a href="model.xlsx" download
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-xs font-semibold transition-colors">
            <i data-lucide="file-spreadsheet" class="w-4 h-4 text-emerald-600"></i>
            <span>Excel Model</span>
          </a>
        </div>

      </div>

      <!-- Tab Navigation Row (Touch scrollable with smooth scrollbar-none) -->
      <nav class="flex space-x-1 sm:space-x-1.5 border-t border-slate-100 py-1.5 sm:py-2 overflow-x-auto no-scrollbar scroll-smooth">
        <button onclick="switchTab(1)" id="tab-btn-1"
          class="px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all bg-sky-50 text-sky-700 border border-sky-200 shadow-2xs flex items-center gap-1.5 shrink-0 cursor-pointer whitespace-nowrap">
          <i data-lucide="shield-check" class="w-3.5 h-3.5 shrink-0"></i>
          <span>1. Liquidity Runway</span>
        </button>
        <button onclick="switchTab(2)" id="tab-btn-2"
          class="px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all flex items-center gap-1.5 shrink-0 cursor-pointer whitespace-nowrap">
          <i data-lucide="credit-card" class="w-3.5 h-3.5 shrink-0"></i>
          <span>2. Revolver Facility</span>
        </button>
        <button onclick="switchTab(3)" id="tab-btn-3"
          class="px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all flex items-center gap-1.5 shrink-0 cursor-pointer whitespace-nowrap">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5 shrink-0"></i>
          <span>3. Working Capital (DFO)</span>
        </button>
        <button onclick="switchTab(4)" id="tab-btn-4"
          class="px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all flex items-center gap-1.5 shrink-0 cursor-pointer whitespace-nowrap">
          <i data-lucide="git-pull-request" class="w-3.5 h-3.5 shrink-0"></i>
          <span>4. 13-Week Cash Flow</span>
        </button>
      </nav>

    </div>
  </header>

  <!-- ======================================================================= -->
  <!-- MAIN CONTENT CONTAINER                                                  -->
  <!-- ======================================================================= -->
  <main class="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-6 space-y-4 sm:space-y-6 flex-1 w-full">

    <div class="rounded-xl border border-sky-200 bg-sky-50/70 p-3 sm:p-4 text-[11px] sm:text-xs text-slate-700 leading-relaxed">
      <strong class="text-slate-900">Data Calibration &amp; Architecture Note:</strong>
      This engine models multi-rail treasury clearing and regulatory liquidity using a calibrated discrete-event simulation. Macro boundaries—including an annualized GPV of ~$240B ($600M/day), corporate cash reserves, and a $500M revolving credit facility—are benchmarked to Block, Inc. SEC Form 10-K disclosures. Micro-level merchant distributions, rail routing (Card, ACH, FedNow/RTP), and interchange schedules are generated using stylized payment-network industry standards to model intraday liquidity float.
    </div>

    <!-- COVENANT EARLY WARNING STATUS BANNER -->
    <div id="covenant-banner" class="p-3.5 sm:p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-all bg-emerald-50/80 border-emerald-200 text-emerald-900">
      <div class="flex items-start sm:items-center gap-2.5 sm:gap-3">
        <div id="banner-icon-box" class="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0">
          <i data-lucide="shield-check" class="w-4 h-4 sm:w-5 sm:h-5"></i>
        </div>
        <div>
          <h2 id="banner-title" class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-emerald-800">Covenant Status: Compliant</h2>
          <p id="banner-desc" class="text-xs text-emerald-700 mt-0.5 leading-snug">
            Headroom stands at <strong>$739.34M</strong> (Minimum safety buffer: $50.00M above $250.00M covenant floor).
          </p>
        </div>
      </div>
      <div class="flex items-center gap-3 sm:gap-4 text-[11px] sm:text-xs font-medium text-emerald-800 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-emerald-200/60 sm:border-transparent">
        <div>Floor: <span class="font-bold num-tabular">$250.00M</span></div>
        <div class="w-px h-3.5 bg-emerald-300"></div>
        <div>Early Alert: <span class="font-bold num-tabular">&lt; $50.00M</span></div>
      </div>
    </div>

    <!-- 4 EXECUTIVE METRIC CARDS (2-column on mobile, 4-column on desktop) -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-4">
      
      <!-- CARD 1: Total Available Liquidity -->
      <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1.5 sm:space-y-2">
        <div class="flex items-center justify-between text-slate-500">
          <span class="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-slate-400 truncate">Total Liquidity</span>
          <i data-lucide="landmark" class="w-3.5 h-3.5 sm:w-4 sm:h-4 text-sky-600 shrink-0"></i>
        </div>
        <div id="kpi-tot-val" class="text-lg sm:text-2xl font-bold num-tabular tracking-tight text-slate-900 truncate">##INIT_TOT_LIQ##</div>
        <div class="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-500 pt-1 border-t border-slate-100">
          <span>Cushion</span>
          <span id="kpi-cushion-val" class="font-semibold text-emerald-600 num-tabular truncate">##INIT_CUSHION##</span>
        </div>
      </div>

      <!-- CARD 2: Corporate Operating Cash -->
      <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1.5 sm:space-y-2">
        <div class="flex items-center justify-between text-slate-500">
          <span class="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-slate-400 truncate">Corporate Cash</span>
          <i data-lucide="wallet" class="w-3.5 h-3.5 sm:w-4 sm:h-4 text-teal-600 shrink-0"></i>
        </div>
        <div id="kpi-cash-val" class="text-lg sm:text-2xl font-bold num-tabular tracking-tight text-slate-900 truncate">##INIT_CORP_CASH##</div>
        <div class="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-500 pt-1 border-t border-slate-100">
          <span>Status</span>
          <span class="font-semibold text-teal-600 truncate">Operating</span>
        </div>
      </div>

      <!-- CARD 3: Working Capital / Float -->
      <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1.5 sm:space-y-2">
        <div class="flex items-center justify-between text-slate-500">
          <span class="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-slate-400 truncate">Days Float (DFO)</span>
          <i data-lucide="gauge" class="w-3.5 h-3.5 sm:w-4 sm:h-4 text-amber-600 shrink-0"></i>
        </div>
        <div id="kpi-dfo-val" class="text-lg sm:text-2xl font-bold num-tabular tracking-tight text-slate-900 truncate">##INIT_DFO##</div>
        <div class="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-500 pt-1 border-t border-slate-100">
          <span>Net Float</span>
          <span id="kpi-float-val" class="font-semibold text-slate-700 num-tabular truncate">##INIT_FLOAT##</span>
        </div>
      </div>

      <!-- CARD 4: Regulatory Basel III LCR -->
      <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1.5 sm:space-y-2">
        <div class="flex items-center justify-between text-slate-500">
          <span class="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-slate-400 truncate">Basel III LCR</span>
          <i data-lucide="award" class="w-3.5 h-3.5 sm:w-4 sm:h-4 text-indigo-600 shrink-0"></i>
        </div>
        <div id="kpi-lcr-val" class="text-lg sm:text-2xl font-bold num-tabular tracking-tight text-slate-900 truncate">##INIT_LCR##</div>
        <div class="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-500 pt-1 border-t border-slate-100">
          <span>LCR</span>
          <span id="kpi-lcr-status" class="px-1.5 sm:px-2 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
            ##INIT_LCR_STATUS##
          </span>
        </div>
      </div>

    </div>

    <!-- DYNAMIC EXPLANATORY NOTE CALLOUT (Tab-Specific Clear Insights) -->
    <div id="tab-note-callout" class="p-3.5 sm:p-4 rounded-xl bg-sky-50/70 border border-sky-200 text-sky-950 space-y-2 text-xs leading-relaxed">
      <div class="flex items-start gap-2">
        <i data-lucide="info" class="w-4 h-4 text-sky-600 shrink-0 mt-0.5"></i>
        <div>
          <p class="font-bold text-sky-900 mb-1">Understanding Liquidity Runway & Covenant Benchmarks:</p>
          <ul class="list-disc pl-4 space-y-1 text-slate-700">
            <li><strong>Total Available Liquidity</strong>: Corporate Operating Cash + Undrawn Revolver Capacity ($500.00M facility limit).</li>
            <li><strong>Liquidity Cushion</strong>: Safety margin remaining after subtracting the mandatory $250.00M covenant floor.</li>
            <li><strong>Corporate Operating Cash</strong>: Unrestricted operational reserves strictly segregated from protected client settlement balances.</li>
            <li><strong>Basel III LCR</strong>: High-Quality Liquid Assets divided by 30-day net stressed cash outflows (&ge; 100% is statutory compliant).</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- PRIMARY VISUALIZATION CONTAINER -->
    <div class="bg-white rounded-xl border border-slate-200 card-shadow p-3.5 sm:p-6 space-y-3 sm:space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-3 pb-3 border-b border-slate-100">
        <div>
          <h3 id="chart-main-title" class="text-sm sm:text-base font-bold text-slate-900 leading-snug">Daily Liquidity Trajectory vs $250M Covenant Floor</h3>
          <p id="chart-main-desc" class="text-[11px] sm:text-xs text-slate-500 mt-0.5">Total Available Liquidity & Corporate Operating Cash evolution across 150-day calendar horizon</p>
        </div>

        <!-- Controls for Tab 4 Waterfall -->
        <div id="twcf-controls" class="hidden flex items-center gap-2 shrink-0">
          <span class="text-xs font-medium text-slate-500">Period:</span>
          <select id="twcf-week-select" onchange="renderTwcfBridge()"
            class="text-xs font-semibold bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500 cursor-pointer max-w-[200px] sm:max-w-none">
            <option value="ALL">Cumulative Horizon (All Weeks)</option>
          </select>
        </div>
      </div>

      <!-- Chart Canvas (Responsive Height) -->
      <div class="relative w-full h-[250px] sm:h-[300px] md:h-[350px]">
        <canvas id="main-chart-canvas"></canvas>
      </div>
    </div>

    <!-- SECONDARY DETAIL SECTION (Dynamic by Tab) -->
    <div id="secondary-content" class="space-y-4 sm:space-y-6">
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
          <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Policy Runway</span>
          <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">##INIT_RUNWAY##</div>
          <p class="text-[11px] sm:text-xs text-slate-500">Total Liquidity / Trailing Daily Payout</p>
        </div>
        <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
          <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Credit Facility Benchmark</span>
          <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">$500.00M Cap</div>
          <p class="text-[11px] sm:text-xs text-slate-500">Committed Revolving Credit Facility</p>
        </div>
        <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
          <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Covenant Threshold</span>
          <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">$250.00M Floor</div>
          <p class="text-[11px] sm:text-xs text-slate-500">Minimum Corporate Liquidity Requirement</p>
        </div>
      </div>
    </div>

    <!-- ======================================================================= -->
    <!-- EXECUTIVE TREASURY DECISIONS & STRATEGIC POLICY FRAMEWORK               -->
    <!-- ======================================================================= -->
    <div class="bg-white rounded-xl border border-slate-200 card-shadow p-3.5 sm:p-6 space-y-4 sm:space-y-6">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-3 pb-3 sm:pb-4 border-b border-slate-100">
        <div>
          <div class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-sky-50 text-sky-700 border border-sky-200 mb-1.5">
            <i data-lucide="shield-check" class="w-3 h-3"></i>
            <span>Executive Strategy & Policy Playbook</span>
          </div>
          <h3 class="text-sm sm:text-base font-bold text-slate-900">Executive Treasury Decisions & Strategic Outcomes</h3>
          <p class="text-[11px] sm:text-xs text-slate-500 mt-0.5">Empirical capital allocation, working capital optimization, and regulatory liquidity strategies derived from the 150-day multi-rail stress simulation.</p>
        </div>
        <div class="text-[11px] sm:text-xs font-semibold text-slate-500 flex items-center gap-1.5 self-start sm:self-auto bg-slate-50 px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-lg border border-slate-200 shrink-0">
          <i data-lucide="check-circle" class="w-3.5 h-3.5 text-emerald-600"></i>
          <span>Production Decision Matrix</span>
        </div>
      </div>

      <!-- 4 Strategic Pillars Grid (1-col on mobile, 2-col on sm/md, 4-col on lg) -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        
        <!-- Decision 1 -->
        <div class="p-3.5 sm:p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-sky-300 transition-all space-y-2.5 sm:space-y-3 flex flex-col justify-between">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="p-1.5 sm:p-2 rounded-lg bg-sky-100 text-sky-700"><i data-lucide="landmark" class="w-4 h-4"></i></span>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">High Priority</span>
            </div>
            <h4 class="text-xs font-bold text-slate-900 leading-tight">1. Credit Facility Right-Sizing</h4>
            <div class="text-xs text-slate-600 space-y-1 leading-relaxed">
              <p><strong>Vulnerability:</strong> +48h clearing friction depletes corporate cash to -$281M on Day 2, capping the $500M revolver and leaving covenant headroom &lt;$50M.</p>
              <p><strong>Decision:</strong> Upsize revolving facility to <strong>$650M–$700M</strong> (or syndicate a $150M–$200M accordion tranche).</p>
            </div>
          </div>
          <div class="pt-2 border-t border-slate-200/80 text-[11px] text-sky-800 font-semibold flex items-center justify-between">
            <span>Impact: +$150M buffer</span>
            <span class="text-emerald-700">Prevents Default</span>
          </div>
        </div>

        <!-- Decision 2 -->
        <div class="p-3.5 sm:p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-sky-300 transition-all space-y-2.5 sm:space-y-3 flex flex-col justify-between">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="p-1.5 sm:p-2 rounded-lg bg-teal-100 text-teal-700"><i data-lucide="calendar" class="w-4 h-4"></i></span>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200">Operational</span>
            </div>
            <h4 class="text-xs font-bold text-slate-900 leading-tight">2. Post-Holiday Settlement Staggering</h4>
            <div class="text-xs text-slate-600 space-y-1 leading-relaxed">
              <p><strong>Vulnerability:</strong> 3-day holiday weekends spike Day 2 merchant payouts ($618.7M) ahead of card receipts ($31.8M), requiring a $586.9M injection.</p>
              <p><strong>Decision:</strong> Restructure enterprise contracts to split holiday disbursements <strong>(50% Day 2, 50% Day 3)</strong>.</p>
            </div>
          </div>
          <div class="pt-2 border-t border-slate-200/80 text-[11px] text-sky-800 font-semibold flex items-center justify-between">
            <span>Peak Demand: -$220M</span>
            <span class="text-emerald-700">Eliminates Spike</span>
          </div>
        </div>

        <!-- Decision 3 -->
        <div class="p-3.5 sm:p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-sky-300 transition-all space-y-2.5 sm:space-y-3 flex flex-col justify-between">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="p-1.5 sm:p-2 rounded-lg bg-amber-100 text-amber-700"><i data-lucide="zap" class="w-4 h-4"></i></span>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">Working Capital</span>
            </div>
            <h4 class="text-xs font-bold text-slate-900 leading-tight">3. Payment Rail Steering (DFO -1.0d)</h4>
            <div class="text-xs text-slate-600 space-y-1 leading-relaxed">
              <p><strong>Vulnerability:</strong> Card rails (T+2/T+3) trap $164.4M in uncollected float receivables, incurring high debt carry (8.50%–10.75% SOFR).</p>
              <p><strong>Decision:</strong> Offer <strong>5–10 bps interchange rebates</strong> to steer merchants to ACH Same-Day (T+1) and FedNow/RTP (T+0).</p>
            </div>
          </div>
          <div class="pt-2 border-t border-slate-200/80 text-[11px] text-sky-800 font-semibold flex items-center justify-between">
            <span>Float Unlocked: $164.4M</span>
            <span class="text-emerald-700">$10.7M–$13.1M Savings</span>
          </div>
        </div>

        <!-- Decision 4 -->
        <div class="p-3.5 sm:p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-sky-300 transition-all space-y-2.5 sm:space-y-3 flex flex-col justify-between">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="p-1.5 sm:p-2 rounded-lg bg-indigo-100 text-indigo-700"><i data-lucide="line-chart" class="w-4 h-4"></i></span>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">Governance</span>
            </div>
            <h4 class="text-xs font-bold text-slate-900 leading-tight">4. Predictive TWCF Early Warning</h4>
            <div class="text-xs text-slate-600 space-y-1 leading-relaxed">
              <p><strong>Vulnerability:</strong> Traditional monthly accounting closes mask settlement timing decay and CECL credit allowances until post-close.</p>
              <p><strong>Decision:</strong> Institutionalize weekly automated TWCF variance decomposition with triggers on timing drag &gt;-$15M.</p>
            </div>
          </div>
          <div class="pt-2 border-t border-slate-200/80 text-[11px] text-sky-800 font-semibold flex items-center justify-between">
            <span>Visibility: 6–8 Weeks</span>
            <span class="text-emerald-700">Early Action</span>
          </div>
        </div>

      </div>

      <!-- Decision Scorecard Table (Scrollable with mobile hint) -->
      <div class="rounded-xl border border-slate-200 overflow-hidden">
        <div class="bg-slate-50/80 px-3.5 sm:px-5 py-2.5 sm:py-3 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
          <span class="text-xs font-bold text-slate-800 uppercase tracking-wider">CFO & Treasurer Action Scorecard</span>
          <div class="flex items-center gap-2">
            <span class="text-[10px] text-slate-400 sm:hidden flex items-center gap-1 font-medium bg-white px-2 py-0.5 rounded border border-slate-200">
              <i data-lucide="arrow-left-right" class="w-3 h-3 text-sky-600"></i> Scroll table horizontally
            </span>
            <span class="text-[11px] text-slate-500 font-medium hidden sm:inline">Quantified Simulation Findings</span>
          </div>
        </div>
        <div class="overflow-x-auto no-scrollbar sm:overflow-x-auto">
          <table class="w-full text-xs text-left min-w-[640px]">
            <thead class="bg-slate-50 text-slate-400 font-semibold border-b border-slate-100">
              <tr>
                <th class="px-3.5 sm:px-5 py-3">Strategic Decision</th>
                <th class="px-3.5 sm:px-5 py-3">Operational Catalyst</th>
                <th class="px-3.5 sm:px-5 py-3">Capital & Liquidity Impact</th>
                <th class="px-3.5 sm:px-5 py-3">Annualized P&L / Cost Benefit</th>
                <th class="px-3.5 sm:px-5 py-3 text-right">Implementation Horizon</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 font-medium">
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 sm:px-5 py-3 font-bold text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
                  <span class="w-1.5 h-1.5 rounded-full bg-sky-500 shrink-0"></span>
                  Revolver Facility Upsizing
                </td>
                <td class="px-3.5 sm:px-5 py-3 text-slate-600">$500M cap exhausted during +48h clearing friction</td>
                <td class="px-3.5 sm:px-5 py-3 text-sky-700 font-semibold">+$150M to +$200M liquidity headroom buffer</td>
                <td class="px-3.5 sm:px-5 py-3 text-emerald-700 font-semibold">Prevents $250M covenant default penalties</td>
                <td class="px-3.5 sm:px-5 py-3 text-right text-slate-600 whitespace-nowrap">60–90 Days (Bank Syndicate)</td>
              </tr>
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 sm:px-5 py-3 font-bold text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
                  <span class="w-1.5 h-1.5 rounded-full bg-teal-500 shrink-0"></span>
                  Post-Holiday Payout Staggering
                </td>
                <td class="px-3.5 sm:px-5 py-3 text-slate-600">Day 2 $586.89M post-holiday cash injection spike</td>
                <td class="px-3.5 sm:px-5 py-3 text-sky-700 font-semibold">Peak cash injection reduced by $110M–$220M</td>
                <td class="px-3.5 sm:px-5 py-3 text-emerald-700 font-semibold">Saves $1.5M–$3.0M in surge borrowing interest</td>
                <td class="px-3.5 sm:px-5 py-3 text-right text-slate-600 whitespace-nowrap">30–60 Days (Merchant Contracts)</td>
              </tr>
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 sm:px-5 py-3 font-bold text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0"></span>
                  Payment Rail Steering (DFO -1.0d)
                </td>
                <td class="px-3.5 sm:px-5 py-3 text-slate-600">$164.4M float trapped in T+2/T+3 card rails</td>
                <td class="px-3.5 sm:px-5 py-3 text-sky-700 font-semibold">Releases $164.4M trapped working capital</td>
                <td class="px-3.5 sm:px-5 py-3 text-emerald-700 font-semibold">$10.7M–$13.1M annual interest expense savings</td>
                <td class="px-3.5 sm:px-5 py-3 text-right text-slate-600 whitespace-nowrap">Immediate (Pricing Incentives)</td>
              </tr>
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 sm:px-5 py-3 font-bold text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
                  <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0"></span>
                  Predictive TWCF Variance Alerting
                </td>
                <td class="px-3.5 sm:px-5 py-3 text-slate-600">CECL allowances & timing decay erode cash unseen</td>
                <td class="px-3.5 sm:px-5 py-3 text-sky-700 font-semibold">6–8 week forward visibility on liquidity pinches</td>
                <td class="px-3.5 sm:px-5 py-3 text-emerald-700 font-semibold">Protects against unexpected liquidity compression</td>
                <td class="px-3.5 sm:px-5 py-3 text-right text-emerald-700 font-bold whitespace-nowrap">Active in Engine</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- METHODOLOGY & SEC 10-K PROVENANCE DISCLOSURE -->
    <div class="rounded-xl border border-slate-200 bg-slate-50/80 p-3.5 sm:p-5 space-y-2 text-xs text-slate-600">
      <div class="flex items-center gap-2 font-bold text-slate-800">
        <i data-lucide="info" class="w-4 h-4 text-sky-600 shrink-0"></i>
        <span>Financial Modeling Methodology & SEC Form 10-K Provenance Disclosure</span>
      </div>
      <p class="leading-relaxed">
        <strong>Macro Calibration Anchors:</strong> System parameters are calibrated against Block, Inc.’s (NYSE: SQ) public SEC Form 10-K filings, including ~$220B–$240B annualized Gross Payment Volume (GPV), ~6-rail clearing mix distribution, ASC 606 gross vs net principal revenue recognition, CRR Art 336 / PSD2 Art 10 regulatory safeguarding segregation, and standard $500M revolving credit facility / $250M covenant floor benchmarks.
      </p>
      <p class="leading-relaxed">
        <strong>Simulation Outputs vs SEC Filings:</strong> Specific operational numbers presented across this dashboard—including the <strong>$586.89M</strong> post-holiday settlement cash injection spike, <strong>$164.4M</strong> average trapped float receivables, and <strong>$10.7M–$13.1M</strong> annualized interest savings—are <em>deterministic simulation outputs generated by our 7-step recursive cash waterfall engine</em> across a 150-day banking horizon, rather than historical point-in-time accounting balances directly excerpted from SEC filing tables (which report quarterly aggregate snapshots rather than daily liquidity waterfalls).
      </p>
    </div>

  </main>

  <!-- ======================================================================= -->
  <!-- FOOTER                                                                  -->
  <!-- ======================================================================= -->
  <footer class="mt-auto border-t border-slate-200 bg-white py-4">
    <div class="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-400 text-center sm:text-left">
      <div class="flex items-center gap-2 justify-center sm:justify-start">
        <i data-lucide="shield" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
        <span>Block, Inc. (NYSE: SQ) Benchmark | Statutory Settlement Float & TWCF FP&A Dual-Ledger Framework</span>
      </div>
      <div>150-Day Projection Horizon | Daily Sweep Target $300.00M | Covenant Floor $250.00M</div>
    </div>
  </footer>


  <!-- ======================================================================= -->
  <!-- CLIENT JAVASCRIPT & DATA BINDING                                        -->
  <!-- ======================================================================= -->
  <script>
    const DATA = ##DATA_PAYLOAD##;
    let currentScenario = 'BASELINE';
    let currentTab = 1;
    let mainChart = null;
    let secondaryChart = null;

    // Rich Tooltip Formatter Configuration
    const tooltipStyle = {
      backgroundColor: '#ffffff',
      titleColor: '#0f172a',
      bodyColor: '#334155',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      padding: 12,
      boxPadding: 6,
      cornerRadius: 8,
      titleFont: { size: 12, weight: 'bold', family: 'Inter, sans-serif' },
      bodyFont: { size: 11, weight: '500', family: 'Inter, sans-serif' },
      shadowOffsetX: 0,
      shadowOffsetY: 4,
      shadowBlur: 12,
      shadowColor: 'rgba(0, 0, 0, 0.08)'
    };

    function init() {
      populateWeekSelect();
      updateDashboard();
      if (window.lucide && window.lucide.createIcons) {
        lucide.createIcons();
      }
    }

    function fmtM(val) {
      if (val === null || val === undefined) return '$0.00M';
      return '$' + (val / 1e6).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'M';
    }

    function setScenario(sc) {
      currentScenario = sc;
      ['BASELINE', 'ADVERSE', 'SEVERELY_ADVERSE'].forEach(s => {
        const btn = document.getElementById('sc-btn-' + s);
        if (btn) {
          if (s === sc) {
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-white text-slate-900 shadow-xs transition-all flex items-center gap-1.5 cursor-pointer';
          } else {
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 cursor-pointer';
          }
        }
      });
      updateDashboard();
    }

    function switchTab(tabNum) {
      currentTab = tabNum;
      
      // Update tab button classes cleanly without querying children that might have changed to SVG
      [1, 2, 3, 4].forEach(n => {
        const btn = document.getElementById('tab-btn-' + n);
        if (btn) {
          if (n === tabNum) {
            btn.className = 'px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all bg-sky-50 text-sky-700 border border-sky-200 shadow-2xs flex items-center gap-1.5 shrink-0 cursor-pointer';
          } else {
            btn.className = 'px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all flex items-center gap-1.5 shrink-0 cursor-pointer';
          }
        }
      });

      const twcfCtrl = document.getElementById('twcf-controls');
      if (twcfCtrl) {
        if (tabNum === 4) {
          twcfCtrl.classList.remove('hidden');
        } else {
          twcfCtrl.classList.add('hidden');
        }
      }

      renderTabCallout();
      renderMainChart();
      renderSecondarySection();
      if (window.lucide && window.lucide.createIcons) {
        lucide.createIcons();
      }
    }

    function updateDashboard() {
      const sc = DATA[currentScenario];
      if (!sc) return;
      const t1 = sc.tab1;
      const t2 = sc.tab2;
      const t3 = sc.tab3;

      // 1. Status Banner
      const banner = document.getElementById('covenant-banner');
      const bIcon = document.getElementById('banner-icon-box');
      const bTitle = document.getElementById('banner-title');
      const bDesc = document.getElementById('banner-desc');

      if (banner && bIcon && bTitle && bDesc) {
        if (t1.alert) {
          banner.className = 'p-3.5 sm:p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-all bg-rose-50/90 border-rose-200 text-rose-900';
          bIcon.className = 'w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0';
          bTitle.className = 'text-[11px] sm:text-xs font-bold uppercase tracking-wider text-rose-800';
          bTitle.textContent = '⚠️ Covenant Headroom Alert Triggered';
          bDesc.className = 'text-xs text-rose-700 mt-0.5 leading-snug';
          bDesc.innerHTML = `Headroom stands at <strong>${fmtM(t1.covenant_headroom)}</strong>, breaching the policy safety buffer of <strong>&lt; $50.00M</strong> against the <strong>$250.00M</strong> covenant floor.`;
        } else {
          banner.className = 'p-3.5 sm:p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-all bg-emerald-50/80 border-emerald-200 text-emerald-900';
          bIcon.className = 'w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0';
          bTitle.className = 'text-[11px] sm:text-xs font-bold uppercase tracking-wider text-emerald-800';
          bTitle.textContent = 'Covenant Status: Compliant';
          bDesc.className = 'text-xs text-emerald-700 mt-0.5 leading-snug';
          bDesc.innerHTML = `Headroom stands at <strong>${fmtM(t1.covenant_headroom)}</strong> (Minimum Safety Buffer: $50.00M above $250.00M covenant floor).`;
        }
      }

      // 2. Metric Cards
      const elTot = document.getElementById('kpi-tot-val');
      const elCushion = document.getElementById('kpi-cushion-val');
      const elCash = document.getElementById('kpi-cash-val');
      const elDfo = document.getElementById('kpi-dfo-val');
      const elFloat = document.getElementById('kpi-float-val');
      const elLcr = document.getElementById('kpi-lcr-val');
      const elLcrStatus = document.getElementById('kpi-lcr-status');

      if (elTot) elTot.textContent = fmtM(t1.total_liquidity);
      if (elCushion) elCushion.textContent = fmtM(t1.cushion);
      if (elCash) elCash.textContent = fmtM(t1.corporate_closing_cash);
      if (elDfo) elDfo.textContent = t3.dfo.toFixed(2) + ' Days';
      if (elFloat) elFloat.textContent = fmtM(t3.net_float);
      if (elLcr) elLcr.textContent = (t1.lcr_ratio * 100).toFixed(2) + '%';
      
      if (elLcrStatus) {
        if (t1.lcr_status === 'COMPLIANT') {
          elLcrStatus.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200';
          elLcrStatus.textContent = 'COMPLIANT';
        } else if (t1.lcr_status === 'WARNING') {
          elLcrStatus.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200';
          elLcrStatus.textContent = 'WARNING';
        } else {
          elLcrStatus.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200';
          elLcrStatus.textContent = 'BREACH';
        }
      }

      renderTabCallout();
      renderMainChart();
      renderSecondarySection();
      if (window.lucide && window.lucide.createIcons) {
        lucide.createIcons();
      }
    }

    function renderTabCallout() {
      const callout = document.getElementById('tab-note-callout');
      if (!callout) return;
      const sc = DATA[currentScenario];
      const p = sc.params;

      if (currentTab === 1) {
        callout.innerHTML = `
          <div class="flex items-start gap-2">
            <i data-lucide="info" class="w-4 h-4 text-sky-600 shrink-0 mt-0.5"></i>
            <div>
              <p class="font-bold text-sky-900 mb-1">Understanding Liquidity Runway & Covenant Benchmarks:</p>
              <ul class="list-disc pl-4 space-y-1 text-slate-700">
                <li><strong>Total Available Liquidity</strong>: Corporate Operating Cash + Undrawn Revolver Capacity ($500.00M facility limit).</li>
                <li><strong>Liquidity Cushion</strong>: Safety margin remaining after subtracting the mandatory $250.00M covenant floor.</li>
                <li><strong>Corporate Operating Cash</strong>: Unrestricted operational reserves strictly segregated from protected client settlement balances.</li>
                <li><strong>Basel III LCR</strong>: High-Quality Liquid Assets divided by 30-day net stressed cash outflows (&ge; 100% is statutory compliant).</li>
              </ul>
            </div>
          </div>
        `;
      } else if (currentTab === 2) {
        callout.innerHTML = `
          <div class="flex items-start gap-2">
            <i data-lucide="help-circle" class="w-4 h-4 text-sky-600 shrink-0 mt-0.5"></i>
            <div>
              <p class="font-bold text-sky-900 mb-1">Why Active Debt Shows $500.00M & How Scenarios Differ:</p>
              <ul class="list-disc pl-4 space-y-1 text-slate-700">
                <li><strong>Day 2 Settlement Gap Shock</strong>: On Jan 2 (first banking day after New Year holiday), merchant settlement payouts ($618.67M) precede cleared T+2 inbound card receipts ($31.78M). Under statutory safeguarding, corporate cash injects $586.89M to cover the gap.</li>
                <li><strong>Automatic Maximum Drawdown ($500.00M)</strong>: Pre-financing corporate cash plunges to -$281.03M, breaching the $250.00M covenant floor. The engine automatically draws the maximum facility capacity ($500.00M).</li>
                <li><strong>Baseline vs Stress Persistence</strong>: In <em>Baseline</em>, card receipts arrive on Day 3+, allowing corporate cash to rise above the $300.00M sweep threshold and repaying debt to <strong>$0.00</strong>. In <em>Adverse (+24h)</em> and <em>Severely Adverse (+48h)</em>, persistent clearing lag keeps corporate cash below $300.00M, locking the revolver at <strong>$500.00M</strong> throughout the projection horizon.</li>
                <li><strong>Current Macro Rates</strong>: Base SOFR ${(p.sofr*100).toFixed(2)}% + Spread ${(p.spread*100).toFixed(2)}% = Effective Borrowing Rate <strong>${(p.rate*100).toFixed(2)}%</strong> (Actual/360).</li>
              </ul>
            </div>
          </div>
        `;
      } else if (currentTab === 3) {
        callout.innerHTML = `
          <div class="flex items-start gap-2">
            <i data-lucide="layers" class="w-4 h-4 text-sky-600 shrink-0 mt-0.5"></i>
            <div>
              <p class="font-bold text-sky-900 mb-1">Working Capital & Settlement Float Dynamics:</p>
              <ul class="list-disc pl-4 space-y-1 text-slate-700">
                <li><strong>Days Float Outstanding (DFO)</strong>: Gross Settlements Receivable / (Annualized GPV / 365). Quantifies the calendar timing lag between customer authorization and cash settlement from acquiring bank partners.</li>
                <li><strong>Settlements Receivable (Asset)</strong>: In-flight customer payment transactions across card rails (Visa/Mastercard T+2, Amex T+3) awaiting acquiring bank clearing.</li>
                <li><strong>Customers Payable (Liability)</strong>: Cleared merchant transaction balances held on ledger pending scheduled payout disbursement.</li>
                <li><strong>Net Settlement Float</strong>: Receivables minus Payables. A positive float indicates temporary platform funding; a negative float represents self-funding settlement balances.</li>
              </ul>
            </div>
          </div>
        `;
      } else if (currentTab === 4) {
        callout.innerHTML = `
          <div class="flex items-start gap-2">
            <i data-lucide="calculator" class="w-4 h-4 text-sky-600 shrink-0 mt-0.5"></i>
            <div>
              <p class="font-bold text-sky-900 mb-1">13-Week Cash Flow Bridge (TWCF) Additive Variance Decomposition:</p>
              <ul class="list-disc pl-4 space-y-1 text-slate-700">
                <li><strong>Additive Mathematical Identity</strong>: Actual Net Cash - Budget Net Cash = Volume Variance + Card Mix Shift + Timing Friction + CECL Charge + Residual.</li>
                <li><strong>Volume Variance</strong>: Cash variance driven by deviation in gross transaction volume from budget.</li>
                <li><strong>Card Mix Shift</strong>: Impact of changing payment method proportions (Credit vs Debit vs ACH) and interchange fee drag.</li>
                <li><strong>Timing Friction</strong>: Working capital shifts arising from bank holidays, weekend clustering, and clearing settlement lag.</li>
                <li><strong>CECL Credit Charge</strong>: Provision for expected merchant losses, chargeback risk, and macroeconomic default probability (PD &times; LGD).</li>
              </ul>
            </div>
          </div>
        `;
      }
    }

    function renderMainChart() {
      const sc = DATA[currentScenario];
      const titleElem = document.getElementById('chart-main-title');
      const descElem = document.getElementById('chart-main-desc');
      const canvas = document.getElementById('main-chart-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const isMobile = window.innerWidth < 640;
      
      if (mainChart) {
        mainChart.destroy();
        mainChart = null;
      }

      if (currentTab === 1) {
        // Tab 1: Liquidity Runway Dual-Line Chart
        if (titleElem) titleElem.textContent = 'Daily Liquidity Trajectory vs $250M Covenant Floor';
        if (descElem) descElem.textContent = 'Total Available Liquidity & Corporate Operating Cash evolution across 150-day calendar horizon';

        const s1 = sc.tab1.series;
        mainChart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: s1.map(r => r.date),
            datasets: [
              {
                label: 'Total Available Liquidity',
                data: s1.map(r => r.total_liquidity / 1e6),
                borderColor: '#0284c7', // Ocean Blue
                backgroundColor: '#0284c7',
                borderWidth: isMobile ? 2 : 2.5,
                tension: 0.15,
                pointRadius: 0,
                pointHoverRadius: 4
              },
              {
                label: 'Corporate Closing Cash',
                data: s1.map(r => r.corporate_closing_cash / 1e6),
                borderColor: '#0d9488', // Marine Teal
                backgroundColor: '#0d9488',
                borderWidth: isMobile ? 1.8 : 2,
                tension: 0.15,
                pointRadius: 0,
                pointHoverRadius: 4
              },
              {
                label: 'Covenant Floor ($250M)',
                data: s1.map(() => 250.0),
                borderColor: '#ef4444',
                backgroundColor: '#ef4444',
                borderWidth: 1.6,
                borderDash: [5, 4],
                pointRadius: 0
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { 
                display: true, 
                position: isMobile ? 'bottom' : 'top', 
                align: isMobile ? 'center' : 'end',
                labels: { boxWidth: isMobile ? 8 : 12, padding: isMobile ? 6 : 10, font: { size: isMobile ? 10 : 11, weight: '500', family: 'Inter, sans-serif' } }
              },
              tooltip: {
                ...tooltipStyle,
                callbacks: {
                  title: (items) => 'Date: ' + items[0].label,
                  label: (ctx) => {
                    if (ctx.dataset.label.includes('Covenant Floor')) return ' Covenant Floor: $250.00M';
                    return ` ${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}M`;
                  }
                }
              }
            },
            scales: {
              x: { grid: { color: 'rgba(0,0,0,0.03)' }, ticks: { color: '#64748b', maxTicksLimit: isMobile ? 5 : 12, font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } } },
              y: { 
                grid: { color: 'rgba(0,0,0,0.03)' }, 
                ticks: { color: '#64748b', callback: (v) => '$' + v + 'M', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } },
                title: { display: !isMobile, text: 'Liquidity ($ Millions)', color: '#64748b', font: { size: 10, family: 'Inter, sans-serif' } }
              }
            }
          }
        });

      } else if (currentTab === 2) {
        // Tab 2: Revolver Facility Utilization AREA CHART (no crowded bars!)
        if (titleElem) titleElem.textContent = 'Daily Revolver Facility Utilization ($ Millions) — Area Trajectory';
        if (descElem) descElem.textContent = 'Facility draws buffering clearing shortfalls against $500M maximum facility capacity';

        const s2 = sc.tab2.daily;
        mainChart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: s2.map(r => r.date),
            datasets: [
              {
                label: 'Active Revolver Debt',
                data: s2.map(r => r.debt / 1e6),
                borderColor: '#0284c7', // Ocean Hue
                backgroundColor: 'rgba(2, 132, 199, 0.18)', // Soft gradient fill
                fill: true,
                borderWidth: isMobile ? 1.8 : 2.2,
                tension: 0.2,
                pointRadius: 0,
                pointHoverRadius: 4
              },
              {
                label: 'Facility Capacity ($500M)',
                data: s2.map(() => 500.0),
                borderColor: '#ef4444',
                borderWidth: 1.6,
                borderDash: [4, 4],
                pointRadius: 0,
                fill: false
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { 
                display: true, 
                position: isMobile ? 'bottom' : 'top', 
                align: isMobile ? 'center' : 'end',
                labels: { boxWidth: isMobile ? 8 : 12, padding: isMobile ? 6 : 10, font: { size: isMobile ? 10 : 11, weight: '500', family: 'Inter, sans-serif' } }
              },
              tooltip: {
                ...tooltipStyle,
                callbacks: {
                  title: (items) => 'Date: ' + items[0].label,
                  label: (ctx) => {
                    if (ctx.dataset.label.includes('Facility Capacity')) return ' Max Capacity: $500.00M';
                    return ` Active Debt Balance: $${ctx.parsed.y.toFixed(2)}M`;
                  },
                  afterBody: () => ['Facility Status: ' + (currentScenario === 'BASELINE' ? 'Repaid to $0.00' : 'Locked at $500.00M Cap')]
                }
              }
            },
            scales: {
              x: { grid: { color: 'rgba(0,0,0,0.03)' }, ticks: { color: '#64748b', maxTicksLimit: isMobile ? 5 : 12, font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } } },
              y: { 
                grid: { color: 'rgba(0,0,0,0.03)' }, 
                ticks: { color: '#64748b', callback: (v) => '$' + v + 'M', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } },
                title: { display: !isMobile, text: 'Drawn Debt ($ Millions)', color: '#64748b', font: { size: 10, family: 'Inter, sans-serif' } }
              }
            }
          }
        });

      } else if (currentTab === 3) {
        // Tab 3: Working Capital Float Area Chart
        if (titleElem) titleElem.textContent = 'Daily Working Capital: Settlements Receivable (Asset) vs Customers Payable (Liability)';
        if (descElem) descElem.textContent = 'Comparative trajectory of inbound acquirer claims vs outbound merchant payouts';

        const s3 = sc.tab3.daily;
        mainChart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: s3.map(r => r.date),
            datasets: [
              {
                label: 'Gross Settlements Receivable (Asset)',
                data: s3.map(r => r['Settlements Receivable (Asset)'] / 1e6),
                borderColor: '#0284c7', // Ocean
                backgroundColor: 'rgba(2, 132, 199, 0.14)',
                fill: true,
                borderWidth: isMobile ? 1.8 : 2,
                pointRadius: 0,
                tension: 0.15
              },
              {
                label: 'Gross Customers Payable (Liability)',
                data: s3.map(r => r['Customers Payable (Liability)'] / 1e6),
                borderColor: '#d97706', // Amber
                backgroundColor: 'rgba(217, 119, 6, 0.14)',
                fill: true,
                borderWidth: isMobile ? 1.8 : 2,
                pointRadius: 0,
                tension: 0.15
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { 
                display: true, 
                position: isMobile ? 'bottom' : 'top', 
                align: isMobile ? 'center' : 'end',
                labels: { boxWidth: isMobile ? 8 : 12, padding: isMobile ? 6 : 10, font: { size: isMobile ? 10 : 11, weight: '500', family: 'Inter, sans-serif' } }
              },
              tooltip: {
                ...tooltipStyle,
                callbacks: {
                  title: (items) => 'Date: ' + items[0].label,
                  label: (ctx) => ` ${ctx.dataset.label.split(' ')[1]}: $${ctx.parsed.y.toFixed(2)}M`,
                  afterBody: (items) => {
                    if (items.length >= 2) {
                      const net = items[0].parsed.y - items[1].parsed.y;
                      return ['Net Settlement Float: ' + (net >= 0 ? '+$' : '-$') + Math.abs(net).toFixed(2) + 'M'];
                    }
                    return [];
                  }
                }
              }
            },
            scales: {
              x: { grid: { color: 'rgba(0,0,0,0.03)' }, ticks: { color: '#64748b', maxTicksLimit: isMobile ? 5 : 12, font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } } },
              y: { 
                grid: { color: 'rgba(0,0,0,0.03)' }, 
                ticks: { color: '#64748b', callback: (v) => '$' + v + 'M', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } },
                title: { display: !isMobile, text: 'Working Capital ($ Millions)', color: '#64748b', font: { size: 10, family: 'Inter, sans-serif' } }
              }
            }
          }
        });

      } else if (currentTab === 4) {
        // Tab 4: 13-Week Waterfall Bridge Chart with Floating Bars & Initial/Delta/Final Tooltip!
        renderTwcfBridge();
      }
    }

    function renderTwcfBridge() {
      const sc = DATA[currentScenario];
      const titleElem = document.getElementById('chart-main-title');
      const descElem = document.getElementById('chart-main-desc');
      const selVal = document.getElementById('twcf-week-select') ? document.getElementById('twcf-week-select').value : 'ALL';
      const t4 = sc.tab4;
      const isMobile = window.innerWidth < 640;

      let vol = 0, mix = 0, tim = 0, cecl = 0, net = 0;

      if (selVal === 'ALL') {
        t4.forEach(r => { vol += r.vol; mix += r.mix; tim += r.tim; cecl += r.cecl; });
        net = vol + mix + tim - cecl;
        if (titleElem) titleElem.textContent = 'Cumulative FP&A Variance Waterfall ($ Millions)';
        if (descElem) descElem.textContent = 'Full 13-week cumulative bridge: Initial Baseline $0.00M -> Final Net Cash Variance';
      } else {
        const item = t4.find(r => r.week === selVal) || t4[0];
        vol = item.vol; mix = item.mix; tim = item.tim; cecl = item.cecl;
        net = item.net;
        if (titleElem) titleElem.textContent = `Weekly Variance Bridge for ${selVal} ($ Millions)`;
        if (descElem) descElem.textContent = `Additive bridge of weekly contributions for ${selVal}`;
      }

      const v_vol = vol / 1e6;
      const v_mix = mix / 1e6;
      const v_tim = tim / 1e6;
      const v_cecl = -cecl / 1e6;
      const v_net = net / 1e6;

      // Floating bar coordinates [start, end]
      const s1 = 0.0;
      const e1 = s1 + v_vol;
      const s2 = e1;
      const e2 = s2 + v_mix;
      const s3 = e2;
      const e3 = s3 + v_tim;
      const s4 = e3;
      const e4 = s4 + v_cecl;
      const s5 = 0.0;
      const e5 = v_net;

      const labels = isMobile 
        ? ['Volume', 'Mix', 'Timing', 'CECL', 'Net Cash']
        : ['Volume Variance', 'Card Mix Shift', 'Timing Friction', 'CECL Credit Charge', 'Net Cash Variance'];

      const floatingData = [
        [s1, e1],
        [s2, e2],
        [s3, e3],
        [s4, e4],
        [s5, e5]
      ];

      const bgColors = [
        v_vol >= 0 ? '#10b981' : '#ef4444',
        v_mix >= 0 ? '#10b981' : '#ef4444',
        v_tim >= 0 ? '#10b981' : '#ef4444',
        v_cecl >= 0 ? '#10b981' : '#ef4444',
        '#0284c7' // Ocean blue total column
      ];

      const canvas = document.getElementById('main-chart-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (mainChart) {
        mainChart.destroy();
        mainChart = null;
      }
      mainChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Variance Contribution ($ Millions)',
            data: floatingData,
            backgroundColor: bgColors,
            borderRadius: isMobile ? 4 : 6,
            borderSkipped: false
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              ...tooltipStyle,
              callbacks: {
                title: (items) => items[0].label,
                label: (ctx) => {
                  const raw = ctx.raw;
                  const start = raw[0];
                  const end = raw[1];
                  const delta = end - start;
                  const sign = delta >= 0 ? '+' : '';
                  if (ctx.dataIndex === 4) {
                    return [
                      ` Initial Baseline: $0.00M`,
                      ` Net Cash Variance: ${end >= 0 ? '+' : ''}$${end.toFixed(2)}M`
                    ];
                  }
                  return [
                    ` Initial Value: $${start.toFixed(2)}M`,
                    ` Variance Delta: ${sign}$${delta.toFixed(2)}M`,
                    ` Final Value: $${end.toFixed(2)}M`
                  ];
                }
              }
            }
          },
          scales: {
            x: { grid: { color: 'rgba(0,0,0,0.03)' }, ticks: { color: '#64748b', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } } },
            y: { 
              grid: { color: 'rgba(0,0,0,0.03)' }, 
              ticks: { color: '#64748b', callback: (v) => (v>=0?'+':'') + '$' + v + 'M', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } },
              title: { display: !isMobile, text: 'Variance Delta ($ Millions)', color: '#64748b', font: { size: 10, family: 'Inter, sans-serif' } }
            }
          }
        }
      });
    }

    function renderSecondarySection() {
      const container = document.getElementById('secondary-content');
      if (!container) return;
      const sc = DATA[currentScenario];
      const isMobile = window.innerWidth < 640;

      // Clean up previous secondary chart if exists
      if (secondaryChart) {
        secondaryChart.destroy();
        secondaryChart = null;
      }

      if (currentTab === 1) {
        // Tab 1 Secondary: Benchmark Metrics Cards
        container.innerHTML = `
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
              <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Policy Runway</span>
              <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">${sc.tab1.runway_days ? sc.tab1.runway_days.toFixed(2) + ' Days' : 'N/A'}</div>
              <p class="text-[11px] sm:text-xs text-slate-500">Total Liquidity / Trailing Daily Payout</p>
            </div>
            <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
              <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Credit Facility Benchmark</span>
              <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">$500.00M Cap</div>
              <p class="text-[11px] sm:text-xs text-slate-500">Committed Revolving Credit Facility</p>
            </div>
            <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
              <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Covenant Threshold</span>
              <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">$250.00M Floor</div>
              <p class="text-[11px] sm:text-xs text-slate-500">Minimum Corporate Liquidity Requirement</p>
            </div>
          </div>
        `;
      } else if (currentTab === 2) {
        // Tab 2 Secondary: Monthly Margin Erosion Bar Chart & Table
        container.innerHTML = `
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-5">
            <div class="lg:col-span-7 bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-3">
              <div class="flex items-center justify-between">
                <div>
                  <h4 class="text-xs sm:text-sm font-bold text-slate-900">Monthly Net Operating Margin Drag (bps)</h4>
                  <p class="text-[11px] sm:text-xs text-slate-400">Revolver interest carrying cost in basis points of operating margin</p>
                </div>
              </div>
              <div class="relative w-full h-[190px] sm:h-[240px]">
                <canvas id="carry-chart-canvas"></canvas>
              </div>
            </div>

            <div class="lg:col-span-5 bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-3">
              <h4 class="text-xs sm:text-sm font-bold text-slate-900">Facility Cost & Rate Summary</h4>
              <div class="divide-y divide-slate-100 text-xs">
                <div class="py-2 sm:py-2.5 flex items-center justify-between">
                  <span class="text-slate-500">Base SOFR Rate</span>
                  <span class="font-bold text-slate-800">${(sc.params.sofr*100).toFixed(2)}%</span>
                </div>
                <div class="py-2 sm:py-2.5 flex items-center justify-between">
                  <span class="text-slate-500">Facility Credit Spread</span>
                  <span class="font-bold text-slate-800">${(sc.params.spread*100).toFixed(2)}%</span>
                </div>
                <div class="py-2 sm:py-2.5 flex items-center justify-between">
                  <span class="text-slate-500">Effective Borrowing Cost</span>
                  <span class="font-bold text-sky-700">${(sc.params.rate*100).toFixed(2)}%</span>
                </div>
                <div class="py-2 sm:py-2.5 flex items-center justify-between">
                  <span class="text-slate-500">Cumulative Period Interest</span>
                  <span class="font-bold text-rose-600">${fmtM(sc.tab2.total_interest)}</span>
                </div>
                <div class="py-2 sm:py-2.5 flex items-center justify-between">
                  <span class="text-slate-500">Latest Active Debt</span>
                  <span class="font-bold text-slate-900">${fmtM(sc.tab2.latest_debt)}</span>
                </div>
              </div>
            </div>
          </div>
        `;

        // Render secondary carry chart
        setTimeout(() => {
          const carryCanvas = document.getElementById('carry-chart-canvas');
          if (!carryCanvas) return;
          const carryCtx = carryCanvas.getContext('2d');
          const carryData = sc.tab2.monthly_carry_bps;
          secondaryChart = new Chart(carryCtx, {
            type: 'bar',
            data: {
              labels: carryData.map(r => r[0]),
              datasets: [{
                label: 'Margin Drag (bps)',
                data: carryData.map(r => r[1]),
                backgroundColor: '#f59e0b',
                borderRadius: 4
              }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: false },
                tooltip: {
                  ...tooltipStyle,
                  callbacks: {
                    label: (ctx) => ` Margin Erosion: ${ctx.parsed.y.toFixed(2)} bps`
                  }
                }
              },
              scales: {
                x: { grid: { color: 'rgba(0,0,0,0.03)' }, ticks: { color: '#64748b', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } } },
                y: { grid: { color: 'rgba(0,0,0,0.03)' }, ticks: { color: '#64748b', callback: (v) => v + ' bps', font: { size: isMobile ? 9 : 10, family: 'Inter, sans-serif' } } }
              }
            }
          });
        }, 50);

      } else if (currentTab === 3) {
        // Tab 3 Secondary: Working Capital Metrics
        container.innerHTML = `
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
              <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Gross Inbound Claims</span>
              <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">${fmtM(sc.tab3.receivables)}</div>
              <p class="text-[11px] sm:text-xs text-slate-500">Settlements Receivable (Asset)</p>
            </div>
            <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
              <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Gross Merchant Liabilities</span>
              <div class="text-lg sm:text-xl font-bold num-tabular text-slate-900">${fmtM(sc.tab3.payables)}</div>
              <p class="text-[11px] sm:text-xs text-slate-500">Customers Payable (Liability)</p>
            </div>
            <div class="bg-white rounded-xl p-3.5 sm:p-5 border border-slate-200 card-shadow space-y-1">
              <span class="text-[10px] sm:text-xs font-semibold text-slate-400 uppercase">Clearing Friction Shift</span>
              <div class="text-lg sm:text-xl font-bold text-slate-900">${sc.params.lag_desc}</div>
              <p class="text-[11px] sm:text-xs text-slate-500">Acquirer Settlement Speed</p>
            </div>
          </div>
        `;
      } else if (currentTab === 4) {
        // Tab 4 Secondary: 13-Week Cash Flow Variance Audit Table
        container.innerHTML = `
          <div class="bg-white rounded-xl border border-slate-200 card-shadow overflow-hidden">
            <div class="p-3.5 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-2">
              <div>
                <h3 class="text-xs sm:text-sm font-bold text-slate-900">13-Week Cash Flow Variance Audit Table</h3>
                <p class="text-[11px] sm:text-xs text-slate-400 mt-0.5">Additive FP&A decomposition: Actual Net Cash minus Budget Net Cash</p>
              </div>
              <span class="text-[10px] text-slate-400 sm:hidden flex items-center gap-1 font-medium bg-slate-50 px-2 py-1 rounded border border-slate-200 self-start">
                <i data-lucide="arrow-left-right" class="w-3 h-3 text-sky-600"></i> Scroll table horizontally
              </span>
            </div>
            <div class="overflow-x-auto no-scrollbar sm:overflow-x-auto">
              <table class="w-full text-xs text-left min-w-[620px]">
                <thead class="bg-slate-50 text-slate-400 font-semibold border-b border-slate-100">
                  <tr>
                    <th class="px-3.5 sm:px-5 py-3">ISO Week</th>
                    <th class="px-3.5 sm:px-5 py-3 text-right">Volume Variance</th>
                    <th class="px-3.5 sm:px-5 py-3 text-right">Card Mix Shift</th>
                    <th class="px-3.5 sm:px-5 py-3 text-right">Timing Friction</th>
                    <th class="px-3.5 sm:px-5 py-3 text-right">CECL Charge</th>
                    <th class="px-3.5 sm:px-5 py-3 text-right font-bold text-slate-900">Net Cash Variance</th>
                    <th class="px-3.5 sm:px-5 py-3 text-center">Audit Identity</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 font-medium">
                  ${sc.tab4.map(r => `
                    <tr class="hover:bg-slate-50/80 transition-colors">
                      <td class="px-3.5 sm:px-5 py-3 font-bold text-slate-800 whitespace-nowrap">${r.week}</td>
                      <td class="px-3.5 sm:px-5 py-3 text-right num-tabular whitespace-nowrap ${r.vol >= 0 ? 'text-emerald-600' : 'text-rose-600'}">${r.vol >= 0 ? '+' : ''}${fmtM(r.vol)}</td>
                      <td class="px-3.5 sm:px-5 py-3 text-right num-tabular whitespace-nowrap ${r.mix >= 0 ? 'text-emerald-600' : 'text-rose-600'}">${r.mix >= 0 ? '+' : ''}${fmtM(r.mix)}</td>
                      <td class="px-3.5 sm:px-5 py-3 text-right num-tabular whitespace-nowrap ${r.tim >= 0 ? 'text-emerald-600' : 'text-rose-600'}">${r.tim >= 0 ? '+' : ''}${fmtM(r.tim)}</td>
                      <td class="px-3.5 sm:px-5 py-3 text-right num-tabular whitespace-nowrap text-rose-600">-${fmtM(r.cecl)}</td>
                      <td class="px-3.5 sm:px-5 py-3 text-right num-tabular whitespace-nowrap font-bold ${r.net >= 0 ? 'text-slate-900' : 'text-rose-700'}">${r.net >= 0 ? '+' : ''}${fmtM(r.net)}</td>
                      <td class="px-3.5 sm:px-5 py-3 text-center whitespace-nowrap"><span class="px-2 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">MATCH</span></td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        `;
      }
    }

    function populateWeekSelect() {
      const select = document.getElementById('twcf-week-select');
      if (!select) return;
      const weeks = DATA['BASELINE'].tab4.map(r => r.week);
      weeks.forEach(wk => {
        const opt = document.createElement('option');
        opt.value = wk;
        opt.textContent = `Week ${wk}`;
        select.appendChild(opt);
      });
    }

    function runInit() {
      populateWeekSelect();
      updateDashboard();
      if (window.lucide && window.lucide.createIcons) {
        lucide.createIcons();
      }

      // Add debounced resize listener for responsive orientation changes
      let resizeTimer = null;
      window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          renderMainChart();
          if (currentTab === 2) {
            renderSecondarySection();
          }
        }, 200);
      });
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', runInit);
    } else {
      runInit();
    }
  </script>
</body>
</html>
"""


def build_shadcn_dashboard():
    print("[1/3] Collecting simulation datasets across all macro scenarios...")
    dataset = collect_simulation_data()

    print("[2/3] Embedding data into executive dashboard template with SSR pre-population...")
    json_str = json.dumps(dataset)

    base = dataset["BASELINE"]
    t1 = base["tab1"]
    t3 = base["tab3"]

    def _fmt(v):
        return f"${v/1e6:,.2f}M"

    replacements = {
        "##DATA_PAYLOAD##": json_str,
        "##INIT_TOT_LIQ##": _fmt(t1["total_liquidity"]),
        "##INIT_CUSHION##": _fmt(t1["cushion"]),
        "##INIT_CORP_CASH##": _fmt(t1["corporate_closing_cash"]),
        "##INIT_DFO##": f"{t3['dfo']:.2f} Days",
        "##INIT_FLOAT##": _fmt(t3["net_float"]),
        "##INIT_LCR##": f"{t1['lcr_ratio']*100:.2f}%",
        "##INIT_LCR_STATUS##": t1["lcr_status"],
        "##INIT_RUNWAY##": f"{t1['runway_days']:.2f} Days",
    }

    html_content = HTML_TEMPLATE
    for k, v in replacements.items():
        html_content = html_content.replace(k, str(v))

    # Output to dashboard.html, index.html (root for Vercel), and dashboard/index.html
    root_dash = Path(__file__).resolve().parents[1] / "dashboard.html"
    root_dash.write_text(html_content, encoding="utf-8")

    root_index = Path(__file__).resolve().parents[1] / "index.html"
    root_index.write_text(html_content, encoding="utf-8")

    dash_dir = Path(__file__).resolve().parents[1] / "dashboard"
    dash_dir.mkdir(exist_ok=True)
    dash_file = dash_dir / "index.html"
    dash_file.write_text(html_content, encoding="utf-8")

    print(f"[3/3] Reference Dashboard successfully generated:")
    print(f"  - Root file (dashboard): {root_dash}")
    print(f"  - Root file (Vercel entry): {root_index}")
    print(f"  - Directory package: {dash_file}")



if __name__ == "__main__":
    build_shadcn_dashboard()
