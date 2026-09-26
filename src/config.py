"""Frozen policy and domain constants. PRD TEXT governs over reference code.

Carry-forwards from reports/phase-00-report.md:
- US calendar: weekends + 11 Federal observances incl. Fri 2026-07-03
  (Independence Day observed; Fed K.8 footnote *).
- EU calendar: ECB T2 euro closings 1 Jan, Good Fri, Easter Mon, 1 May,
  25 Dec, 26 Dec + weekends.
- LCR run-off overlay 30% (PRD text, not code's 0.35). Labeled assumption.
- GPV is the EAD-proxy for CECL (labeled assumption, Phase 4 quantifies).
- Scale freeze: baseline 600M/day governs over 650M call-site (I-11).
"""
from datetime import date
from decimal import Decimal

CAL_START = date(2026, 1, 1)
CAL_END = date(2026, 12, 31)

# 11 US Federal observances in 2026 (Independence Day observed Fri Jul 3
# because Jul 4 is a Saturday; Board closed, Reserve Banks open per K.8).
FED_HOLIDAYS_2026_OBSERVED = frozenset({
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Washington's Birthday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 10, 12),  # Columbus Day
    date(2026, 11, 11),  # Veterans Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas Day
})

# ECB T2 euro-settlement closings 2026. Easter 2026 = Sun Apr 5, so
# Good Friday = Apr 3, Easter Monday = Apr 6. 26 Dec is a Saturday
# (already non-banking) but listed for completeness.
T2_EURO_CLOSURES_2026 = frozenset({
    date(2026, 1, 1),
    date(2026, 4, 3),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 12, 25),
    date(2026, 12, 26),
})

RISK_TIERS = ("TIER_1", "TIER_2", "TIER_3", "TIER_4")
PAYOUT_CONTRACTS = ("NEXT_DAY_T1", "SAME_DAY_RTP", "TWO_DAY_T2")
PAYMENT_RAILS = (
    "CARD_VISA", "CARD_MC", "CARD_AMEX",
    "ACH_STANDARD", "ACH_SAME_DAY", "RTP_FEDNOW",
)

# Tier -> (reserve_rate, hold_days). TIER_1 0% and TIER_4 10%/180d are per
# PRD 5.1; TIER_2/TIER_3 interpolate inside the PRD 5%-10% / 90-180d band
# (documented assumption; Phase 2 enforces it in routing).
RISK_TIER_RESERVE = {
    "TIER_1": (Decimal("0.00"), 0),
    "TIER_2": (Decimal("0.05"), 90),
    "TIER_3": (Decimal("0.075"), 120),
    "TIER_4": (Decimal("0.10"), 180),
}

MIN_CORP_LIQUIDITY_COVENANT = Decimal("250000000")
TARGET_CORP_LIQUIDITY = Decimal("300000000")
REVOLVER_CAPACITY = Decimal("500000000")
OPENING_CORP_CASH = Decimal("300000000")

BASELINE_DAILY_GPV = 600_000_000.0
WEEKEND_VOLUME_MULTIPLIER = 1.30
GENERATION_SEED = 42


def reserve_for_tier(risk_tier, gross_amount):
    """Rolling-reserve deduction for a tier and gross amount (Phase 1 helper)."""
    rate, _ = RISK_TIER_RESERVE[risk_tier]
    return (Decimal(str(gross_amount)) * rate).quantize(Decimal("0.01"))
