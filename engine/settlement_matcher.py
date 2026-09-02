"""
Phase 2: Settlement Batch Matching (Razorpay ↔ Bank)

Groups Razorpay transactions by settlement_id, sums net amounts,
and matches against bank deposits.
"""
import pandas as pd
from datetime import timedelta
from typing import Tuple

AMOUNT_TOLERANCE = 1.0  # ₹1 rounding tolerance
DATE_TOLERANCE_DAYS = 1  # ±1 day


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
        phase1_matched: Matched results from Phase 1 (to get settlement mapping)

    Returns:
        settlement_matches: list of settlement match dicts
        anomalies: list of anomaly dicts
        unmatched_bank: DataFrame of bank deposits not matched
    """
    settlement_matches = []
    anomalies = []

    # Group Razorpay transactions by settlement_id
    settlement_groups = razorpay_df.groupby("settlement_id")

    matched_utr_numbers = set()
    matched_settlement_ids = set()

    for setl_id, group in settlement_groups:
        expected_total = round(group["net_amount"].sum(), 2)
        settlement_date = group["settlement_date"].iloc[0]
        order_ids = group["order_id"].tolist()

        # Search bank statement for matching deposit
        best_match = None
        best_diff = float("inf")

        for _, b_row in bank_df.iterrows():
            if b_row["utr_number"] in matched_utr_numbers:
                continue

            amount_diff = abs(float(b_row["deposit_amount"]) - expected_total)

            # Check date proximity
            b_date = b_row["deposit_date"]
            if isinstance(settlement_date, str):
                from datetime import date as dt_date
                settlement_date = dt_date.fromisoformat(settlement_date)

            date_diff = abs((b_date - settlement_date).days) if hasattr(b_date, '__sub__') else 999

            # Check description for settlement_id using regex (handles bank text noise)
            import re
            desc_text = str(b_row.get("description", ""))
            extracted_setls = re.findall(r"(setl_[a-zA-Z0-9]+)", desc_text)
            desc_match = str(setl_id) in extracted_setls or str(setl_id) in desc_text

            if amount_diff < AMOUNT_TOLERANCE and date_diff <= DATE_TOLERANCE_DAYS:
                if amount_diff < best_diff:
                    best_diff = amount_diff
                    best_match = b_row
            elif desc_match and amount_diff < AMOUNT_TOLERANCE * 5:
                # Looser amount tolerance if description explicitly mentions settlement
                if amount_diff < best_diff:
                    best_diff = amount_diff
                    best_match = b_row

        if best_match is not None:
            note = None
            if best_diff > 0.01:
                note = f"Rounding difference of ₹{best_diff:.2f}"

            settlement_matches.append({
                "settlement_id": str(setl_id),
                "expected_amount": expected_total,
                "bank_amount": float(best_match["deposit_amount"]),
                "utr_number": best_match["utr_number"],
                "settlement_date": str(settlement_date),
                "deposit_date": str(best_match["deposit_date"]),
                "order_count": len(order_ids),
                "order_ids": order_ids,
                "status": "matched" if best_diff < 0.01 else "matched_with_note",
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
                    "expected_total": expected_total,
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
                    "deposit_amount": float(b_row["deposit_amount"]),
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
