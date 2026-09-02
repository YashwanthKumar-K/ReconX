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

MAX_SUBSET_SIZE = 3  # Realistic split payouts are at most 2-3 tranches
DATE_WINDOW_DAYS = 2  # Only consider items within ±2 days
AMOUNT_TOLERANCE = 2.0  # ₹2 tolerance for matching
MAX_CANDIDATES = 15  # Prune to top 15 closest candidates to avoid combinatorial explosion


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

        # Prune candidates to the closest subset by amount
        if len(candidates) > MAX_CANDIDATES:
            candidates = sorted(candidates, key=lambda c: abs(c["net_amount"] - target))[:MAX_CANDIDATES]

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

    # ── Direction 2: One settlement matched by multiple bank deposits ──────────
    # This covers SPLIT_SETTLEMENT: bank splits one large payout into several deposits.
    # Compute intermediate still-unmatched lists for Direction 2 to iterate over.
    still_unmatched_rz = [
        rz for rz in unmatched_razorpay_nets
        if rz.get("id", rz.get("settlement_id", "")) not in matched_razorpay_ids
    ]
    still_unmatched_bank = [
        dep for dep in unmatched_bank_deposits
        if dep["utr_number"] not in matched_bank_utrs
    ]

    for rz in list(still_unmatched_rz):
        rz_id = rz.get("id", rz.get("settlement_id", ""))
        if rz_id in matched_razorpay_ids:
            continue

        target = rz["net_amount"]
        rz_date = rz.get("settlement_date")

        # Filter unmatched bank deposits by date window
        bank_candidates = []
        for dep in still_unmatched_bank:
            if dep["utr_number"] in matched_bank_utrs:
                continue
            dep_date = dep["deposit_date"]
            if rz_date and dep_date:
                try:
                    from datetime import date as dt_date
                    if isinstance(rz_date, str):
                        rz_date_parsed = dt_date.fromisoformat(rz_date)
                    else:
                        rz_date_parsed = rz_date
                    if isinstance(dep_date, str):
                        dep_date_parsed = dt_date.fromisoformat(dep_date)
                    else:
                        dep_date_parsed = dep_date
                    if abs((dep_date_parsed - rz_date_parsed).days) > DATE_WINDOW_DAYS:
                        continue
                except (ValueError, TypeError):
                    pass
            bank_candidates.append(dep)

        if not bank_candidates:
            continue

        # Prune bank candidates to the closest subset
        if len(bank_candidates) > MAX_CANDIDATES:
            bank_candidates = sorted(bank_candidates, key=lambda c: abs(c["deposit_amount"] - target))[:MAX_CANDIDATES]

        # Try combinations of bank deposits that sum to the settlement
        found = False
        for subset_size in range(2, min(MAX_SUBSET_SIZE + 1, len(bank_candidates) + 1)):
            if found:
                break
            for combo in combinations(bank_candidates, subset_size):
                combo_total = sum(c["deposit_amount"] for c in combo)
                diff = abs(combo_total - target)
                if diff <= AMOUNT_TOLERANCE:
                    utrs = [c["utr_number"] for c in combo]
                    for utr in utrs:
                        matched_bank_utrs.add(utr)
                    matched_razorpay_ids.add(rz_id)
                    matches.append({
                        "type": "split_settlement_match",
                        "settlement_id": rz_id,
                        "settlement_amount": target,
                        "matched_deposits": utrs,
                        "matched_total": round(combo_total, 2),
                        "difference": round(diff, 2),
                        "order_ids": rz.get("order_ids", []),
                        "subset_size": subset_size,
                        "status": "matched",
                        "phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                        "note": (
                            f"Settlement {rz_id} (Rs.{target}) matched by {subset_size} "
                            f"bank deposits totaling Rs.{round(combo_total, 2)} "
                            f"(diff: Rs.{round(diff, 2)}). This is a SPLIT_SETTLEMENT."
                        ),
                    })
                    found = True
                    break

    # Recompute still_unmatched after both directions
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
