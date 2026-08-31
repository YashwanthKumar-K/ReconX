"""
Reconciliation Engine — Main Orchestrator

Runs all 4 phases in sequence, collects results, and produces the final report.
"""
import time
import pandas as pd
from typing import Optional
from dotenv import load_dotenv

from engine.csv_parser import load_all_data
from engine.direct_matcher import run_phase1
from engine.settlement_matcher import run_phase2
from engine.graph_matcher import run_phase3
from engine.ai_investigator import investigate_batch
from engine.scorer import score_results


def run_reconciliation(
    data_dir: str = "data/sample",
    use_ai: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Run the full 4-phase reconciliation pipeline.

    Args:
        data_dir: Path to directory containing the 4 CSV files.
        use_ai: Whether to invoke AI for Phase 4 (set False for testing without API key).
        verbose: Print progress to stdout.

    Returns:
        Complete reconciliation report dict.
    """
    load_dotenv()

    if verbose:
        print("=" * 60)
        print("  ReconX -- Multi-Way Ledger Reconciliation Engine")
        print("=" * 60)

    start_time = time.time()

    # ─── Load Data ────────────────────────────────────────────────────────
    if verbose:
        print("\n[1/5] Loading data...")
    data = load_all_data(data_dir)
    merchant_df = data["merchant"]
    razorpay_df = data["razorpay"]
    bank_df = data["bank"]
    ground_truth_df = data["ground_truth"]

    if verbose:
        print(f"  Merchant orders:       {len(merchant_df)}")
        print(f"  Razorpay transactions: {len(razorpay_df)}")
        print(f"  Bank deposits:         {len(bank_df)}")

    # ─── Phase 1: Direct Key Matching ─────────────────────────────────────
    if verbose:
        print("\n[2/5] Phase 1: Direct Key Matching...")
    p1_matched, p1_anomalies, unmatched_merchant, unmatched_razorpay = run_phase1(
        merchant_df, razorpay_df
    )
    p1_stats = {
        "phase_name": "Phase 1: Direct Key Matching",
        "input_count": len(merchant_df),
        "matched_count": len(p1_matched),
        "anomaly_count": len(p1_anomalies),
        "remaining_count": len(unmatched_merchant),
    }
    if verbose:
        print(f"  Matched: {len(p1_matched)} | Anomalies: {len(p1_anomalies)} | Remaining: {len(unmatched_merchant)}")

    # ─── Phase 2: Settlement Batch Matching ───────────────────────────────
    if verbose:
        print("\n[3/5] Phase 2: Settlement Batch Matching...")
    p2_matches, p2_anomalies, unmatched_bank = run_phase2(
        razorpay_df, bank_df, p1_matched
    )
    p2_stats = {
        "phase_name": "Phase 2: Settlement Batch Matching",
        "input_count": len(bank_df),
        "matched_count": len(p2_matches),
        "anomaly_count": len(p2_anomalies),
        "remaining_count": len(unmatched_bank),
    }
    if verbose:
        print(f"  Settlements matched: {len(p2_matches)} | Anomalies: {len(p2_anomalies)} | Unmatched bank: {len(unmatched_bank)}")

    # ─── Phase 3: Bounded Fuzzy/Subset-Sum Matching ───────────────────────
    if verbose:
        print("\n[4/5] Phase 3: Bounded Subset-Sum Matching...")

    # Prepare unmatched items for Phase 3
    # Unmatched settlements from Phase 2
    unmatched_rz_for_p3 = []
    for a in p2_anomalies:
        if a["anomaly_type"] == "SETTLEMENT_MISMATCH":
            rz_data = a.get("razorpay_data", {})
            unmatched_rz_for_p3.append({
                "id": rz_data.get("settlement_id", ""),
                "settlement_id": rz_data.get("settlement_id", ""),
                "net_amount": rz_data.get("expected_total", 0),
                "settlement_date": rz_data.get("settlement_date", ""),
                "order_ids": rz_data.get("order_ids", []),
            })

    unmatched_bank_for_p3 = []
    for a in p2_anomalies:
        if a["anomaly_type"] == "ORPHAN_DEPOSIT":
            b_data = a.get("bank_data", {})
            unmatched_bank_for_p3.append({
                "utr_number": b_data.get("utr_number", ""),
                "deposit_amount": b_data.get("deposit_amount", 0),
                "deposit_date": b_data.get("deposit_date", ""),
                "description": b_data.get("description", ""),
            })

    p3_matches, p3_still_unmatched = run_phase3(unmatched_rz_for_p3, unmatched_bank_for_p3)
    p3_stats = {
        "phase_name": "Phase 3: Fuzzy/Subset-Sum Matching",
        "input_count": len(unmatched_rz_for_p3) + len(unmatched_bank_for_p3),
        "matched_count": len(p3_matches),
        "anomaly_count": 0,
        "remaining_count": len(p3_still_unmatched),
    }
    if verbose:
        print(f"  Subset matches: {len(p3_matches)} | Still unmatched: {len(p3_still_unmatched)}")

    # ─── Phase 4: AI Anomaly Investigation ────────────────────────────────
    if verbose:
        print("\n[5/5] Phase 4: AI Anomaly Investigation...")

    # Collect all anomalies for AI investigation.
    # SETTLEMENT_MISMATCH and ORPHAN_DEPOSIT are excluded here —
    # Phase 3 re-adds them via p3_still_unmatched if genuinely unresolved.
    all_anomalies = p1_anomalies + [
        a for a in p2_anomalies
        if a["anomaly_type"] not in ("SETTLEMENT_MISMATCH", "ORPHAN_DEPOSIT")
    ]

    # Add back unmatched from Phase 3 as anomalies
    for item in p3_still_unmatched:
        if item.get("source") == "razorpay":
            all_anomalies.append({
                "order_id": f"SETTLEMENT_{item.get('settlement_id', 'unknown')}",
                "anomaly_type": "SETTLEMENT_MISMATCH",
                "detected_in_phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                "razorpay_data": item,
                "note": "Could not match this settlement even with fuzzy subset-sum matching.",
            })
        elif item.get("source") == "bank":
            all_anomalies.append({
                "order_id": f"BANK_{item.get('utr_number', 'unknown')}",
                "anomaly_type": "ORPHAN_DEPOSIT",
                "detected_in_phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                "bank_data": item,
                "note": "Bank deposit could not be matched to any combination of settlements.",
            })

    # Add successful split settlement matches as anomalies (they are matched financially, but are still exceptions)
    for match in p3_matches:
        if match.get("type") == "split_settlement_match":
            all_anomalies.append({
                "order_id": f"SETTLEMENT_{match.get('settlement_id', 'unknown')}",
                "anomaly_type": "SPLIT_SETTLEMENT",
                "detected_in_phase": "Phase 3: Fuzzy/Subset-Sum Matching",
                "razorpay_data": {
                    "settlement_id": match.get("settlement_id"),
                    "order_ids": match.get("order_ids", [])
                },
                "note": match.get("note", "Split settlement resolved via Phase 3"),
            })

    # Investigate with AI
    enriched_anomalies = investigate_batch(all_anomalies, use_ai=use_ai)
    
    p4_stats = {
        "phase_name": "Phase 4: AI Anomaly Investigation",
        "input_count": len(all_anomalies),
        "anomaly_count": len(all_anomalies),
        "explained_count": sum(1 for a in enriched_anomalies if "resolution" in a),
        "remaining_count": len(all_anomalies),
    }

    if verbose:
        print(f"  Anomalies investigated: {p4_stats['explained_count']}")
        print(f"  Needs manual review: {p4_stats['remaining_count']}")

    # ─── Scoring ──────────────────────────────────────────────────────────
    matched_order_ids = set(m["order_id"] for m in p1_matched)
    if ground_truth_df is not None:
        if verbose:
            print("\n[SCORING] Evaluating against ground truth...")
        scores = score_results(enriched_anomalies, ground_truth_df, matched_order_ids)
        if verbose:
            print(f"  Engine detection accuracy: {scores['engine_accuracy']}%")
            print(f"  AI classification accuracy: {scores['ai_accuracy']}% ({scores['ai_correct']}/{scores['ai_total']})")
            if scores["undetected_anomalies"]:
                print(f"  Undetected anomalies: {len(scores['undetected_anomalies'])}")
                for u in scores["undetected_anomalies"]:
                    print(f"    - {u['order_id']}: {u['missed_anomaly_type']}")
    else:
        # No ground truth available (user-uploaded data) -- skip scoring
        scores = {
            "engine_accuracy": None,
            "ai_accuracy": None,
            "ai_correct": 0,
            "ai_total": 0,
            "undetected_anomalies": [],
            "confusion_matrix": {},
        }

    elapsed = round(time.time() - start_time, 2)

    # ─── Build Final Report ───────────────────────────────────────────────
    total_matched = len(p1_matched)
    total_records = len(merchant_df)
    match_rate = round((total_matched / total_records) * 100, 1) if total_records > 0 else 0

    report = {
        "total_merchant_orders": len(merchant_df),
        "total_razorpay_transactions": len(razorpay_df),
        "total_bank_deposits": len(bank_df),
        "total_matched": total_matched,
        "total_anomalies": len(enriched_anomalies),
        "match_rate": match_rate,
        "phase_stats": [p1_stats, p2_stats, p3_stats, p4_stats],
        "matched_results": p1_matched,
        "settlement_matches": p2_matches,
        "subset_matches": p3_matches,
        "anomalies": enriched_anomalies,
        "scores": scores,
        "elapsed_seconds": elapsed,
    }

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"  RECONCILIATION COMPLETE in {elapsed}s")
        print(f"  Match rate: {match_rate}% ({total_matched}/{total_records})")
        print(f"  Total anomalies: {len(enriched_anomalies)}")
        print(f"  Engine accuracy: {scores['engine_accuracy']}%")
        print(f"  AI accuracy: {scores['ai_accuracy']}%")
        print(f"{'=' * 60}")

    return report


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data/sample"
    use_ai = "--no-ai" not in sys.argv

    report = run_reconciliation(data_dir=data_dir, use_ai=use_ai)

    # Print anomaly details
    print("\n--- ANOMALY DETAILS ---")
    for a in report["anomalies"]:
        conf = a.get('ai_confidence', '?').upper()
        oid = a.get('order_id', '?')
        atype = a.get('ai_classification', a.get('anomaly_type', '?'))
        explanation = a.get('ai_explanation', a.get('note', ''))
        # Sanitize for Windows console
        explanation = explanation.encode('ascii', 'replace').decode('ascii')
        print(f"\n  [{conf}] {oid}")
        print(f"  Type: {atype}")
        print(f"  {explanation}")
        if a.get("ai_suggested_resolution"):
            res = a['ai_suggested_resolution'].encode('ascii', 'replace').decode('ascii')
            print(f"  Resolution: {res}")

