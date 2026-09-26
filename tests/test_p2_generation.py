"""Phase 2 tests B: normalization + grain generation (tiers, reserves, determinism)."""
import sys
from datetime import date
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402
from src.transactions import (  # noqa: E402
    seed_merchants, normalize_merchant_row, generate_synthetic_transactions,
    ANCHOR_MERCHANTS, RAIL_SHARE)
from src.validation import validate  # noqa: E402


def _seeded():
    con = initialize_database()
    seed_merchants(con)
    return con


def test_d1_anchor_merchants_cover_tiers_contracts():
    con = _seeded()
    assert con.execute("SELECT COUNT(*) FROM dim_merchant").fetchone()[0] == 12
    tiers = set(r[0] for r in con.execute("SELECT DISTINCT risk_tier FROM dim_merchant").fetchall())
    contracts = set(r[0] for r in con.execute(
        "SELECT DISTINCT payout_contract_type FROM dim_merchant").fetchall())
    assert tiers == {"TIER_1", "TIER_2", "TIER_3", "TIER_4"}
    assert contracts == {"NEXT_DAY_T1", "SAME_DAY_RTP", "TWO_DAY_T2"}
    assert len(ANCHOR_MERCHANTS) == 12
    con.close()


def test_d2_normalize_rejects_bad_rows():
    with pytest.raises(ValueError):
        normalize_merchant_row("m", "5411", "TIER_9", "NEXT_DAY_T1")
    with pytest.raises(ValueError):
        normalize_merchant_row("m", "5411", "TIER_1", "WEEKLY")
    with pytest.raises(ValueError):
        normalize_merchant_row("m", "541", "TIER_1", "NEXT_DAY_T1")
    assert normalize_merchant_row("m", "5411", "TIER_4", "TWO_DAY_T2") == (
        "m", "5411", "TIER_4", "TWO_DAY_T2")


def test_d3_generation_grain_counts_and_conservation():
    con = _seeded()
    n = generate_synthetic_transactions(con, num_days=7)
    assert n == 7 * 72
    assert validate(con) == []
    per_day = con.execute("SELECT auth_date, COUNT(*), SUM(gross_amount) FROM fact_transactions "
                          "GROUP BY auth_date ORDER BY auth_date").fetchall()
    assert len(per_day) == 7 and all(r[1] == 72 for r in per_day)
    day0 = con.execute("SELECT SUM(gross_amount) FROM fact_transactions "
                       "WHERE auth_date = '2026-01-01'").fetchone()[0]
    assert abs(float(day0) - 600_000_000.0 * 1.0 * 1.009) / 600_000_000.0 < 0.10
    wknd = con.execute("SELECT SUM(gross_amount) FROM fact_transactions "
                       "WHERE auth_date IN ('2026-01-03','2026-01-04')").fetchone()[0]
    wkday = con.execute("SELECT SUM(gross_amount) FROM fact_transactions "
                        "WHERE auth_date IN ('2026-01-06','2026-01-07')").fetchone()[0]
    assert float(wknd) / float(wkday) > 1.15


def test_d4_tiered_reserves_not_flat():
    con = _seeded()
    generate_synthetic_transactions(con, num_days=3)
    rows = con.execute("SELECT m.risk_tier, "
                       "SUM(t.gross_amount), SUM(t.reserve_retained_amount) "
                       "FROM fact_transactions t JOIN dim_merchant m USING (merchant_id) "
                       "GROUP BY m.risk_tier ORDER BY m.risk_tier").fetchall()
    rates = {r[0]: float(r[2]) / float(r[1]) for r in rows}
    assert abs(rates["TIER_1"] - 0.00) < 1e-9
    assert abs(rates["TIER_2"] - 0.05) < 1e-9
    assert abs(rates["TIER_3"] - 0.075) < 1e-9
    assert abs(rates["TIER_4"] - 0.10) < 1e-9


def test_d5_all_six_rails_and_determinism():
    con = _seeded()
    generate_synthetic_transactions(con, num_days=5)
    rails = set(r[0] for r in con.execute(
        "SELECT DISTINCT payment_rail FROM fact_transactions").fetchall())
    assert rails == set(RAIL_SHARE)
    snap = con.execute("SELECT transaction_id, gross_amount, merchant_payout_date, "
                       "inbound_settlement_date FROM fact_transactions "
                       "ORDER BY transaction_id LIMIT 5").fetchall()
    con2 = _seeded()
    generate_synthetic_transactions(con2, num_days=5)
    snap2 = con2.execute("SELECT transaction_id, gross_amount, merchant_payout_date, "
                         "inbound_settlement_date FROM fact_transactions "
                         "ORDER BY transaction_id LIMIT 5").fetchall()
    assert snap == snap2
    assert con.execute("SELECT COUNT(*) FROM fact_transactions "
                       "WHERE inbound_settlement_date < auth_date OR "
                       "merchant_payout_date < auth_date").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM fact_transactions t JOIN dim_merchant m "
                       "USING (merchant_id) WHERE t.reserve_retained_amount > t.gross_amount"
                       ).fetchone()[0] == 0
    con.close()
    con2.close()


def test_d6_generation_requires_seed():
    from src.database import initialize_database as init2
    con = init2()
    with pytest.raises(RuntimeError):
        generate_synthetic_transactions(con, num_days=2)
    con.close()
    _ = date(2026, 1, 1)
