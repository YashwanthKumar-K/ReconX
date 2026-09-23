"""
Phase 2: Settlement Batch Matching (Razorpay ↔ Bank)

Groups Razorpay transactions by settlement_id, sums net amounts,
and matches against bank deposits.
Uses Decimal for all monetary sums to avoid float drift.
"""
import re
import pandas as pd
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple

AMOUNT_TOLERANCE = Decimal("1.00")   # ₹1 rounding tolerance (strict branch)
DATE_TOLERANCE_DAYS = 1              # ±1 day (strict branch)
DESC_AMOUNT_TOLERANCE = Decimal("5.00")  # ₹5 looser tolerance on description branch
DESC_DATE_TOLERANCE_DAYS = 7         # ±7 days gate on description branch (was unlimited)

# Regex for exact settlement-ID token extraction from bank narration
_SETL_TOKEN_RE = re.compile(r"\b(setl_[a-zA-Z0-9]+)\b", re.IGNORECASE)


def _d(v) -> Decimal:
    """Convert numeric value to Decimal with 2 dp (ROUND_HALF_UP)."""
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def run_phase2(
    razorpay_df: pd.DataFrame,
    bank_df: pd.DataFrame,
    phase1_matched: list[dict],
) -> Tuple[list[dict], list[dict], pd.DataFrame]:
    """
    Phase 2: Match settlement batches to bank deposits.

    Args:
        razorpay_df: Full Razorpay DataFrame (we need all txns for settlement grouping)
        bank_df: Bank statement DataFrame
        phase1_matched: Matched results from Phase 1 — used to exclude duplicate
                        payment IDs from the batch net-amount sum so they don't
                        inflate the expected total.

    Returns:
        settlement_matches: list of settlement match dicts
        anomalies: list of anomaly dicts
        unmatched_bank: DataFrame of bank deposits not matched
    """
    settlement_matches = []
    anomalies = []

    # ── Build exclusion set from Phase 1 duplicates ───────────────────────
    # Duplicate payments were flagged in Phase 1; exclude them from batch sums
    # so a double-charged payment doesn't inflate the expected settlement total.
    p1_anomaly_payment_ids: set[str] = set()
    for m in phase1_matched:
        atype = m.get("anomaly_type", "")
        if atype == "DUPLICATE_PAYMENT":
            rz_data = m.get("razorpay_data", [])
            if isinstance(rz_data, list):
                for r in rz_data:
                    p1_anomaly_payment_ids.add(str(r.get("payment_id", "")))

    # Filter out duplicate payment IDs from the Razorpay frame before grouping
    rz_clean = (
        razorpay_df[~razorpay_df["payment_id"].astype(str).isin(p1_anomaly_payment_ids)]
        if p1_anomaly_payment_ids
        else razorpay_df
    )

    # Group Razorpay transactions by settlement_id
    settlement_groups = rz_clean.groupby("settlement_id")

    matched_utr_numbers = set()
    matched_settlement_ids = set()

    for setl_id, group in settlement_groups:
        # Use Decimal sum to avoid float accumulation error across many rows
        net_sum = sum((_d(v) for v in group["net_amount"]), Decimal("0.00"))
        expected_total = net_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        settlement_date = group["settlement_date"].iloc[0]
        order_ids = group["order_id"].tolist()

        # Search bank statement for matching deposit
        best_match = None
        best_diff = Decimal("999999.99")

        for _, b_row in bank_df.iterrows():
            if b_row["utr_number"] in matched_utr_numbers:
                continue

            dep_amount = _d(b_row["deposit_amount"])
            amount_diff = abs(dep_amount - expected_total)

            # Check date proximity — parse either value if still a string
            b_date = b_row["deposit_date"]
            if isinstance(settlement_date, str):
                from datetime import date as dt_date
                settlement_date = dt_date.fromisoformat(settlement_date)
            if isinstance(b_date, str):
                from datetime import date as dt_date
                try:
                    b_date = dt_date.fromisoformat(b_date)
                except ValueError:
                    b_date = None

            date_diff = abs((b_date - settlement_date).days) if b_date is not None and hasattr(b_date, "__sub__") else 999


            # Exact-token settlement-ID matching (not substring — avoids setl_001 ⊂ setl_0012)
            desc_text = str(b_row.get("description", ""))
            extracted_setls = set(_SETL_TOKEN_RE.findall(desc_text.lower()))
            desc_match = str(setl_id).lower() in extracted_setls

            if amount_diff < AMOUNT_TOLERANCE and date_diff <= DATE_TOLERANCE_DAYS:
                if amount_diff < best_diff:
                    best_diff = amount_diff
                    best_match = b_row
            elif desc_match and amount_diff < DESC_AMOUNT_TOLERANCE and date_diff <= DESC_DATE_TOLERANCE_DAYS:
                # Description branch: looser amount tolerance BUT requires date gate
                if amount_diff < best_diff:
                    best_diff = amount_diff
                    best_match = b_row

        if best_match is not None:
            note = None
            if best_diff > Decimal("0.01"):
                note = f"Rounding difference of ₹{best_diff}"

            settlement_matches.append({
                "settlement_id": str(setl_id),
                "expected_amount": float(expected_total),
                "bank_amount": float(_d(best_match["deposit_amount"])),
                "utr_number": best_match["utr_number"],
                "settlement_date": str(settlement_date),
                "deposit_date": str(best_match["deposit_date"]),
                "order_count": len(order_ids),
                "order_ids": order_ids,
                "status": "matched" if best_diff < Decimal("0.01") else "matched_with_note",
                "phase": "Phase 2: Settlement Batch Matching",
                "note": note,
            })
            matched_utr_numbers.add(best_match["utr_number"])
            matched_settlement_ids.add(str(setl_id))
        else:
            # Settlement not found in bank — could be split or missing
            anomalies.append({
                "order_id": f"SETTLEMENT_{setl_id}",
                "anomaly_type": "SETTLEMENT_MISMATCH",
                "detected_in_phase": "Phase 2: Settlement Batch Matching",
                "merchant_data": None,
                "razorpay_data": {
                    "settlement_id": str(setl_id),
                    "expected_total": float(expected_total),
                    "transaction_count": len(order_ids),
                    "order_ids": order_ids,
                    "settlement_date": str(settlement_date),
                },
                "note": (
                    f"Settlement {setl_id} (₹{expected_total}, {len(order_ids)} orders) "
                    f"has no matching bank deposit."
                ),
            })

    # Find orphan bank deposits (not linked to any settlement)
    for _, b_row in bank_df.iterrows():
        if b_row["utr_number"] not in matched_utr_numbers:
            anomalies.append({
                "order_id": f"BANK_{b_row['utr_number']}",
                "anomaly_type": "ORPHAN_DEPOSIT",
                "detected_in_phase": "Phase 2: Settlement Batch Matching",
                "merchant_data": None,
                "razorpay_data": None,
                "bank_data": {
                    "utr_number": b_row["utr_number"],
                    "deposit_amount": float(_d(b_row["deposit_amount"])),
                    "deposit_date": str(b_row["deposit_date"]),
                    "description": b_row["description"],
                },
                "note": (
                    f"Bank deposit {b_row['utr_number']} (₹{b_row['deposit_amount']}) "
                    f"does not match any Razorpay settlement."
                ),
            })

    # Unmatched bank deposits
    unmatched_bank = bank_df[~bank_df["utr_number"].isin(matched_utr_numbers)].copy()

    return settlement_matches, anomalies, unmatched_bank

