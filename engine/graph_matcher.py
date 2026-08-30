"""
Phase 3: Bounded Fuzzy & Subset-Sum Matching

For remaining unmatched items, uses graph-based matching with bounded search
to find combinations of Razorpay transactions that sum to unmatched bank deposits.

Bounded: max subset size 3-4, date window ±2 days, DP with pruning.
"""
import pandas as pd
from datetime import timedelta
from itertools import combinations
from typing import Tuple

MAX_SUBSET_SIZE = 4  # Cap at 4 items per combination
DATE_WINDOW_DAYS = 2  # Only consider items within ±2 days
AMOUNT_TOLERANCE = 2.0  # ₹2 tolerance for matching


def run_phase3(
    unmatched_razorpay_nets: list[dict],
    unmatched_bank_deposits: list[dict],
) -> Tuple[list[dict], list[dict]]:
    """
    Phase 3: Bounded subset-sum matching.

    Tries to find small subsets of unmatched Razorpay net amounts that sum
    to an unmatched bank deposit.

    Args:
        unmatched_razorpay_nets: list of dicts with {settlement_id, net_amount, settlement_date, order_ids}
        unmatched_bank_deposits: list of dicts with {utr_number, deposit_amount, deposit_date, description}

    Returns:
        matches: list of subset match dicts
        still_unmatched: list of items that couldn't be matched
    """
    matches = []
    matched_razorpay_ids = set()
    matched_bank_utrs = set()

    # Sort deposits descending — try to match largest first
    sorted_deposits = sorted(unmatched_bank_deposits, key=lambda x: x["deposit_amount"], reverse=True)

    for deposit in sorted_deposits:
        if deposit["utr_number"] in matched_bank_utrs:
            continue

        target = deposit["deposit_amount"]
        deposit_date = deposit["deposit_date"]

        # Filter candidates by date window
        candidates = []
        for rz in unmatched_razorpay_nets:
            if rz.get("id", rz.get("settlement_id", "")) in matched_razorpay_ids:
                continue

            # Date proximity check
            rz_date = rz.get("settlement_date")
            if rz_date and deposit_date:
                try:
                    from datetime import date as dt_date
                    if isinstance(rz_date, str):
                        rz_date = dt_date.fromisoformat(rz_date)
                    if isinstance(deposit_date, str):
                        deposit_date_parsed = dt_date.fromisoformat(deposit_date)
                    else:
                        deposit_date_parsed = deposit_date
                    date_diff = abs((deposit_date_parsed - rz_date).days)
                    if date_diff > DATE_WINDOW_DAYS:
                        continue
                except (ValueError, TypeError):
                    pass  # If date parsing fails, still consider the candidate

            candidates.append(rz)

        if not candidates:
            continue

        # Try combinations of size 1 to MAX_SUBSET_SIZE
        found = False
        for subset_size in range(1, min(MAX_SUBSET_SIZE + 1, len(candidates) + 1)):
            if found:
                break

            for combo in combinations(candidates, subset_size):
                combo_total = sum(c["net_amount"] for c in combo)
                diff = abs(combo_total - target)

                if diff <= AMOUNT_TOLERANCE:
                    # Found a match!
                    combo_ids = []
                    combo_orders = []
                    for c in combo:
                        cid = c.get("id", c.get("settlement_id", "unknown"))
                        combo_ids.append(cid)
                        matched_razorpay_ids.add(cid)
                        combo_orders.extend(c.get("order_ids", []))

                    matches.append({
                        "type": "subset_match",
                        "bank_utr": deposit["utr_number"],
                        "bank_amount": target,
                        "matched_settlements": combo_ids,
                        "matched_total": round(combo_total, 2),
                        "difference": round(diff, 2),
                        "order_ids": combo_orders,
                        "subset_size": subset_size,
                        "status": "matched",
                        "phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                        "note": (
                            f"Matched bank deposit {deposit['utr_number']} (Rs.{target}) "
                            f"to {subset_size} settlement(s) totaling Rs.{round(combo_total, 2)} "
                            f"(diff: Rs.{round(diff, 2)})."
                        ),
                    })
                    matched_bank_utrs.add(deposit["utr_number"])
                    found = True
                    break

    # Collect still unmatched items
    still_unmatched_rz = [
        rz for rz in unmatched_razorpay_nets
        if rz.get("id", rz.get("settlement_id", "")) not in matched_razorpay_ids
    ]
    still_unmatched_bank = [
        dep for dep in unmatched_bank_deposits
        if dep["utr_number"] not in matched_bank_utrs
    ]

    still_unmatched = []
    for rz in still_unmatched_rz:
        still_unmatched.append({
            "type": "unmatched_settlement",
            "source": "razorpay",
            **rz,
        })
    for dep in still_unmatched_bank:
        still_unmatched.append({
            "type": "unmatched_deposit",
            "source": "bank",
            **dep,
        })

    return matches, still_unmatched
