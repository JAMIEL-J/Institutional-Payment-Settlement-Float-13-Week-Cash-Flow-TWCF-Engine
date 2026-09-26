"""Phase 1 focused tests B: dictionary tables, PKs, domains, FK, grain insert."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import initialize_database  # noqa: E402
from src.validation import validate  # noqa: E402


def test_b1_tables_exist_empty_with_pk():
    con = initialize_database()
    for tbl in ("dim_merchant", "fact_transactions",
                "fpa_cash_waterfall_daily", "fpa_regulatory_liquidity_daily"):
        n = con.execute("SELECT COUNT(*) FROM duckdb_constraints() WHERE table_name = ? "
                        "AND constraint_type = 'PRIMARY KEY'", [tbl]).fetchone()[0]
        assert n >= 1, tbl
        assert con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] == 0
    con.close()


def test_b2_output_column_shapes():
    con = initialize_database()
    wf = [r[0] for r in con.execute("DESCRIBE fpa_cash_waterfall_daily").fetchall()]
    assert wf == ["ledger_date", "safeguarded_opening_cash", "safeguarded_inbound_settlements",
                  "safeguarded_outbound_payouts", "safeguarded_net_float_delta",
                  "corporate_subordination_injection", "corporate_opening_cash",
                  "net_revenue_swept", "pre_financing_corporate_cash", "revolver_draw_amount",
                  "revolver_repayment_amount", "active_debt_balance",
                  "daily_interest_expense", "corporate_closing_cash"]
    liq = [r[0] for r in con.execute("DESCRIBE fpa_regulatory_liquidity_daily").fetchall()]
    assert liq == ["ledger_date", "total_hqla_level1", "stressed_30d_net_outflows",
                   "lcr_ratio", "lcr_status", "cecl_daily_allowance", "covenant_liquidity_cushion"]
    con.close()


def test_b3_pk_and_fk_rejected():
    con = initialize_database()
    con.execute("INSERT INTO dim_merchant VALUES ('m1','5411','TIER_4','NEXT_DAY_T1')")
    with pytest.raises(Exception):
        con.execute("INSERT INTO dim_merchant VALUES ('m1','5411','TIER_1','NEXT_DAY_T1')")
    with pytest.raises(Exception):
        con.execute("INSERT INTO fact_transactions VALUES ('t-orphan','ghost',"
                    "TIMESTAMP '2026-01-05 10:00:00', DATE '2026-01-05','CARD_VISA',"
                    "100.00, 1.80, 2.75, 0.00, DATE '2026-01-06', DATE '2026-01-07')")
    assert validate(con) == []
    con.close()


def test_b4_grain_insert_passes():
    con = initialize_database()
    con.execute("INSERT INTO dim_merchant VALUES ('m1','5411','TIER_4','NEXT_DAY_T1')")
    con.execute("INSERT INTO fact_transactions VALUES ('t1','m1',"
                "TIMESTAMP '2026-01-05 10:00:00', DATE '2026-01-05','CARD_VISA',"
                "100.00, 1.80, 2.75, 10.00, DATE '2026-01-06', DATE '2026-01-07')")
    assert validate(con) == []
    row = con.execute("SELECT gross_amount, reserve_retained_amount FROM fact_transactions "
                      "WHERE transaction_id='t1'").fetchone()
    assert float(row[0]) == 100.00 and float(row[1]) == 10.00
    con.close()
