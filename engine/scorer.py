"""
Scorer: Evaluates engine + AI accuracy against ground truth.

Compares the reconciliation engine's anomaly detection and the AI's
classification against ground_truth.csv (the private answer key).
"""
import pandas as pd
from typing import Optional


# Mapping from AI classifications back to ground truth anomaly types
AI_TO_GROUND_TRUTH_MAP = {
    "TIMING_MISMATCH": "TIMING_MISMATCH",
    "TIMING_ISSUE": "TIMING_MISMATCH",
    "PARTIAL_REFUND": "PARTIAL_REFUND",
    "SPLIT_SETTLEMENT": "SPLIT_SETTLEMENT",
    "DUPLICATE_PAYMENT": "DUPLICATE_PAYMENT",
    "MISSING_RECORD": "MISSING_IN_RAZORPAY",
    "MISSING_IN_RAZORPAY": "MISSING_IN_RAZORPAY",
    "MISSING_IN_MERCHANT": "MISSING_IN_MERCHANT",
    "FEE_DISCREPANCY": "FEE_DISCREPANCY",
    "REQUIRES_MANUAL_REVIEW": "REQUIRES_MANUAL_REVIEW",
}


def score_results(
    anomalies: list[dict],
    ground_truth_df: pd.DataFrame,
    all_matched_order_ids: set[str],
) -> dict:
    """
    Score the reconciliation results against ground truth.

    Measures:
    1. Engine detection accuracy: Did the engine correctly identify anomalous vs clean records?
    2. AI classification accuracy: For anomalies sent to AI, did it classify the type correctly?

    Args:
        anomalies: List of anomaly dicts (with ai_classification if AI was invoked)
        ground_truth_df: DataFrame with order_id and injected_anomaly_type
        all_matched_order_ids: Set of order_ids that were cleanly matched

    Returns:
        Dict with scoring metrics
    """
    gt_dict = dict(zip(
        ground_truth_df["order_id"],
        ground_truth_df["injected_anomaly_type"],
    ))

    # ─── Engine Detection Accuracy ────────────────────────────────────────
    # Did the engine correctly flag anomalous records and pass clean ones?
    engine_correct = 0
    engine_total = 0
    seen_order_ids = set()  # Prevent any order being scored twice

    # Check clean matches — should be NONE in ground truth
    for oid in all_matched_order_ids:
        if oid in gt_dict and oid not in seen_order_ids:
            seen_order_ids.add(oid)
            engine_total += 1
            if gt_dict[oid] == "NONE":
                engine_correct += 1

    # Check flagged anomalies — should NOT be NONE in ground truth
    anomaly_order_ids = set()
    for a in anomalies:
        oid = a.get("order_id", "")

        if oid.startswith("SETTLEMENT_") or oid.startswith("BANK_"):
            # Extract individual order_ids from settlement-level anomalies
            # Only count orders that actually have an injected anomaly
            rz_data = a.get("razorpay_data", {})
            if isinstance(rz_data, dict):
                sub_order_ids = rz_data.get("order_ids", [])
                for sub_oid in sub_order_ids:
                    if sub_oid in gt_dict and sub_oid not in seen_order_ids:
                        seen_order_ids.add(sub_oid)
                        anomaly_order_ids.add(sub_oid)
                        engine_total += 1
                        if gt_dict[sub_oid] != "NONE":
                            engine_correct += 1  # Correctly flagged an anomalous order
            continue

        if oid not in seen_order_ids:
            seen_order_ids.add(oid)
            anomaly_order_ids.add(oid)
            if oid in gt_dict:
                engine_total += 1
                if gt_dict[oid] != "NONE":
                    engine_correct += 1

    engine_accuracy = round(engine_correct / engine_total * 100, 1) if engine_total > 0 else 0.0

    # ─── AI Classification Accuracy ───────────────────────────────────────
    # For anomalies where AI was invoked, did it get the type right?
    ai_correct = 0
    ai_total = 0
    ai_details = []

    for a in anomalies:
        oid = a.get("order_id", "")
        ai_class = a.get("ai_classification")
        if not ai_class:
            continue
        if oid not in gt_dict:
            continue

        gt_type = gt_dict[oid]
        if gt_type == "NONE":
            continue  # Skip clean records that were wrongly flagged

        ai_total += 1
        # Normalize the AI classification
        normalized_ai = AI_TO_GROUND_TRUTH_MAP.get(ai_class, ai_class)

        is_correct = normalized_ai == gt_type
        if is_correct:
            ai_correct += 1

        ai_details.append({
            "order_id": oid,
            "ground_truth": gt_type,
            "ai_classification": ai_class,
            "normalized": normalized_ai,
            "correct": is_correct,
        })

    ai_accuracy = round(ai_correct / ai_total * 100, 1) if ai_total > 0 else 0.0

    # ─── Confusion matrix (simplified) ────────────────────────────────────
    confusion = {}
    for detail in ai_details:
        gt = detail["ground_truth"]
        pred = detail["normalized"]
        if gt not in confusion:
            confusion[gt] = {}
        confusion[gt][pred] = confusion[gt].get(pred, 0) + 1

    # ─── Undetected anomalies ─────────────────────────────────────────────
    # Ground truth says anomaly, but engine didn't flag it
    undetected = []
    for oid, gt_type in gt_dict.items():
        if gt_type != "NONE" and oid in all_matched_order_ids and oid not in anomaly_order_ids:
            undetected.append({"order_id": oid, "missed_anomaly_type": gt_type})

    return {
        "engine_accuracy": engine_accuracy,
        "engine_correct": engine_correct,
        "engine_total": engine_total,
        "ai_accuracy": ai_accuracy,
        "ai_correct": ai_correct,
        "ai_total": ai_total,
        "ai_details": ai_details,
        "confusion_matrix": confusion,
        "undetected_anomalies": undetected,
    }
