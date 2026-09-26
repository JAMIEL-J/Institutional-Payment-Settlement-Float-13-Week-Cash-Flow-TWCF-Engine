"""Phase 5 tests: week convention, forecast window, additive reconciliation."""
import sys
import datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402
from src.transactions import seed_merchants, generate_synthetic_transactions  # noqa: E402
from src.waterfall import execute_daily_waterfall_engine  # noqa: E402
from src.twcf import (  # noqa: E402
    forecast_13w, weekly_variance, week_key, iso_week_bounds, EPS_TOL)
from src.transactions import RAIL_SHARE  # noqa: E402
from src.config import BASELINE_DAILY_GPV  # noqa: E402


def _ready(days=100):
    con = initialize_database()
    seed_merchants(con)
    generate_synthetic_transactions(con, num_days=days)
    execute_daily_waterfall_engine(con)
    return con


def test_g1_week_convention_iso():
    assert week_key(dt.date(2026, 1, 1)) == "2026-W01"
    assert week_key(dt.date(2026, 1, 4)) == "2026-W01"
    assert week_key(dt.date(2026, 1, 5)) == "2026-W02"
    s, e = iso_week_bounds(dt.date(2026, 1, 7))
    assert (s, e) == (dt.date(2026, 1, 5), dt.date(2026, 1, 11))


def test_g2_forecast_13w_window():
    con = _ready()
    fc = forecast_13w(con, dt.date(2026, 1, 1))
    assert len(fc) == 13
    total = sum(w["forecast_net"] for w in fc)
    ledger = con.execute("SELECT SUM(safeguarded_inbound_settlements"
                         " - safeguarded_outbound_payouts)"
                         " FROM (SELECT * FROM fpa_cash_waterfall_daily"
                         " WHERE ledger_date > '2026-01-01'"
                         " ORDER BY ledger_date LIMIT 91)").fetchone()[0]
    assert abs(total - float(ledger)) < 1.0
    con.close()


def test_g3_additive_reconciliation_with_shifted_forecast():
    con = _ready(60)
    fc = forecast_13w(con, dt.date(2026, 1, 1))
    shift = {w["week_start"].isocalendar()[1]: w for w in fc}
    import datetime as _d
    fim = {}
    for wk_start_iso, w in shift.items():
        pass
    base = weekly_variance(con)
    assert (base["volume_variance"] + base["timing_variance"]
            + base["mix_variance"] + base["residual_eps"]
            - (base["actual_net_cash"] - base["budget_net_cash"])).abs().max() < 1.0
    nz = base[base["actual_gpv"] > 1000000]
    big = nz[(nz["actual_net_cash"] - nz["budget_net_cash"]).abs() > 1000000]
    rel = (big["residual_eps"].abs() / (big["actual_net_cash"] - big["budget_net_cash"]).abs()).max()
    assert rel < 100.0
    con.close()


def test_g4_timing_shift_detected_and_holiday_week():
    """Variance window = weeks with actual data; holiday week excluded."""
    con = _ready(60)
    df = weekly_variance(con)
    wk = df[df["week_key"] == "2026-W02"].iloc[0]
    assert abs(float(wk["timing_variance"])) < 1.0
    fim = {row["week_key"]: sum(float(r[1]) for r in con.execute(
        "SELECT CAST(inbound_settlement_date AS VARCHAR), SUM(gross_amount)"
        " FROM fact_transactions WHERE inbound_settlement_date BETWEEN ? AND ?"
        " GROUP BY 1", [row["week_start"], row["week_end"]]).fetchall())
        for _, row in df.iterrows()}
    shifted = dict(fim)
    shifted["2026-W02"] = fim["2026-W02"] - 1_000_000.0
    df2 = weekly_variance(con, forecast_inbound=shifted)
    wk2 = df2[df2["week_key"] == "2026-W02"].iloc[0]
    assert abs(float(wk2["timing_variance"]) - 1_000_000.0) < 1.0
    assert len(df2) == len(df)
    assert len(df[df["week_key"] == "2026-W27"]) == 0
    assert df["week_end"].max().date() < dt.date(2026, 5, 1)
    con.close()


def test_g5_mix_path_and_budget_scaling():
    """Mix driver must respond to a shifted budget mix; budget scales by days."""
    con = _ready(60)
    base = weekly_variance(con)
    shifted = dict(RAIL_SHARE)
    for r in shifted:
        shifted[r] = 0.0
    shifted["CARD_AMEX"] = 1.0
    mix_df = weekly_variance(con, budget_mix=shifted)
    assert mix_df["mix_variance"].abs().max() > 1_000_000
    plain = weekly_variance(con)
    assert plain["mix_variance"].abs().max() < 1.0
    wk = plain[plain["week_key"] == "2026-W02"].iloc[0]
    assert float(wk["budget_gpv"]) == BASELINE_DAILY_GPV * 7
    assert float(plain.iloc[0]["budget_gpv"]) == BASELINE_DAILY_GPV * 4
    con.close()
