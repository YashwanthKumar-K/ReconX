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
from decimal import Decimal, ROUND_HALF_UP

from engine.config import config

MAX_SUBSET_SIZE = 3  # Realistic split payouts are at most 2-3 tranches
DATE_WINDOW_DAYS = 2  # Only consider items within ±2 days
MAX_CANDIDATES = 15  # Prune candidates to avoid combinatorial explosion


def _d(v) -> Decimal:
    """Convert numeric value to Decimal with 2 dp (ROUND_HALF_UP)."""
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _prune_candidates(candidates: list[dict], target, amount_key: str, max_count: int) -> list[dict]:
    """
    Balanced candidate selection: preserves both large anchor amounts (closest to target)
    and small fraction amounts (to fill remainder splits like 9900 + 50 + 50 = 10000).
    """
    if len(candidates) <= max_count:
        return candidates
    half = max_count // 2
    target_d = _d(target)
    closest = sorted(candidates, key=lambda c: abs(_d(c[amount_key]) - target_d))[:half]
    closest_ids = {id(c) for c in closest}
    remaining = [c for c in candidates if id(c) not in closest_ids]
    smallest = sorted(remaining, key=lambda c: _d(c[amount_key]))[:(max_count - len(closest))]
    return closest + smallest


def run_phase3(
    unmatched_razorpay_nets: list[dict],
    unmatched_bank_deposits: list[dict],
) -> Tuple[list[dict], list[dict]]:
    """
    Phase 3: Bounded subset-sum matching.

    Tries to find small subsets of unmatched Razorpay net amounts that sum
    to an unmatched bank deposit (merged settlements), or subsets of bank deposits
    that sum to a single settlement (split payouts).
    """
    tolerance = _d(getattr(config, "phase3_amount_tolerance", 2.0))
    matches = []
    matched_razorpay_ids = set()
    matched_bank_utrs = set()

    # Sort deposits descending — try to match largest first
    sorted_deposits = sorted(unmatched_bank_deposits, key=lambda x: _d(x["deposit_amount"]), reverse=True)

    for deposit in sorted_deposits:
        if deposit["utr_number"] in matched_bank_utrs:
            continue

        target = _d(deposit["deposit_amount"])
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
                    pass  # If date parsing fails, skip or ignore

            candidates.append(rz)

        if not candidates:
            continue

        # Prune candidates using balanced strategy (closest + smallest)
        candidates = _prune_candidates(candidates, target, "net_amount", MAX_CANDIDATES)

        # Try combinations of size 1 to MAX_SUBSET_SIZE
        found = False
        for subset_size in range(1, min(MAX_SUBSET_SIZE + 1, len(candidates) + 1)):
            if found:
                break

            for combo in combinations(candidates, subset_size):
                combo_total = sum((_d(c["net_amount"]) for c in combo), Decimal("0.00"))
                diff = abs(combo_total - target)

                if diff <= tolerance:
                    # Guard: If subset_size == 1, require narration match to prevent accidental false matches
                    if subset_size == 1:
                        cid = combo[0].get("id", combo[0].get("settlement_id", ""))
                        desc = str(deposit.get("description", "")).lower()
                        if str(cid).lower() not in desc:
                            continue

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
                        "matched_total": combo_total,
                        "difference": diff,
                        "order_ids": combo_orders,
                        "subset_size": subset_size,
                        "status": "matched",
                        "phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                        "note": (
                            f"Matched bank deposit {deposit['utr_number']} (₹{target}) "
                            f"to {subset_size} settlement(s) totaling ₹{combo_total} "
                            f"(diff: ₹{diff})."
                        ),
                    })
                    matched_bank_utrs.add(deposit["utr_number"])
                    found = True
                    break

    # ── Direction 2: One settlement matched by multiple bank deposits ──────────
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

        target = _d(rz["net_amount"])
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

        # Prune bank candidates using balanced strategy
        bank_candidates = _prune_candidates(bank_candidates, target, "deposit_amount", MAX_CANDIDATES)

        # Try combinations of bank deposits that sum to the settlement
        found = False
        for subset_size in range(2, min(MAX_SUBSET_SIZE + 1, len(bank_candidates) + 1)):
            if found:
                break
            for combo in combinations(bank_candidates, subset_size):
                combo_total = sum((_d(c["deposit_amount"]) for c in combo), Decimal("0.00"))
                diff = abs(combo_total - target)
                if diff <= tolerance:

                    utrs = [c["utr_number"] for c in combo]
                    for utr in utrs:
                        matched_bank_utrs.add(utr)
                    matched_razorpay_ids.add(rz_id)
                    matches.append({
                        "type": "split_settlement_match",
                        "settlement_id": rz_id,
                        "settlement_amount": target,
                        "matched_deposits": utrs,
                        "matched_total": combo_total,
                        "difference": diff,
                        "order_ids": rz.get("order_ids", []),
                        "subset_size": subset_size,
                        "status": "matched",
                        "phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                        "note": (
                            f"Settlement {rz_id} (₹{target}) matched by {subset_size} "
                            f"bank deposits totaling ₹{combo_total} "
                            f"(diff: ₹{diff}). This is a SPLIT_SETTLEMENT."
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
