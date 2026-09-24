"""
Unit tests for ReconX engine components:
- direct_matcher (Phase 1)
- settlement_matcher (Phase 2)
- graph_matcher (Phase 3)
- scorer (Phase 5)
- csv_parser
"""
import pytest
import pandas as pd

from engine.direct_matcher import run_phase1
from engine.settlement_matcher import run_phase2
from engine.graph_matcher import run_phase3
from engine.scorer import score_results
from engine.csv_parser import validate_columns, CSVValidationError


# ─── Direct Matcher Tests (Phase 1) ──────────────────────────────────────────

def test_phase1_clean_match():
    merchant_df = pd.DataFrame([{
        "order_id": "ORD_001",
        "amount": 1000.0,
        "order_date": "2026-08-20 10:00:00",
        "status": "completed",
    }])
    razorpay_df = pd.DataFrame([{
        "order_id": "ORD_001",
        "payment_id": "pay_001",
        "settlement_id": "setl_001",
        "amount": 1000.0,
        "fee": 20.0,
        "tax": 3.6,
        "net_amount": 976.4,
        "payment_date": "2026-08-20 10:01:00",
        "settlement_date": "2026-08-21",
        "status": "captured",
    }])

    matched, anomalies, _, _ = run_phase1(merchant_df, razorpay_df)
    assert len(matched) == 1
    assert len(anomalies) == 0
    assert matched[0]["order_id"] == "ORD_001"


def test_phase1_missing_in_razorpay():
    merchant_df = pd.DataFrame([{
        "order_id": "ORD_MISSING",
        "amount": 500.0,
        "order_date": "2026-08-20 10:00:00",
        "status": "completed",
    }])
    razorpay_df = pd.DataFrame(columns=[
        "order_id", "payment_id", "settlement_id", "amount", "fee", "tax", "net_amount", "payment_date", "settlement_date", "status"
    ])

    matched, anomalies, _, _ = run_phase1(merchant_df, razorpay_df)
    assert len(matched) == 0
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "MISSING_RECORD"


def test_phase1_duplicate_payment():
    merchant_df = pd.DataFrame([{
        "order_id": "ORD_DUP",
        "amount": 1000.0,
        "order_date": "2026-08-20 10:00:00",
        "status": "completed",
    }])
    razorpay_df = pd.DataFrame([
        {
            "order_id": "ORD_DUP",
            "payment_id": "pay_DUP_1",
            "settlement_id": "setl_001",
            "amount": 1000.0,
            "fee": 20.0,
            "tax": 3.6,
            "net_amount": 976.4,
            "payment_date": "2026-08-20 10:01:00",
            "settlement_date": "2026-08-21",
            "status": "captured",
        },
        {
            "order_id": "ORD_DUP",
            "payment_id": "pay_DUP_2",
            "settlement_id": "setl_001",
            "amount": 1000.0,
            "fee": 20.0,
            "tax": 3.6,
            "net_amount": 976.4,
            "payment_date": "2026-08-20 10:02:00",
            "settlement_date": "2026-08-21",
            "status": "captured",
        },
    ])

    matched, anomalies, _, _ = run_phase1(merchant_df, razorpay_df)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "DUPLICATE_PAYMENT"


def test_phase1_fee_and_tax_discrepancies():
    # Test abnormal fee rate
    merchant_df = pd.DataFrame([{
        "order_id": "ORD_FEE",
        "amount": 1000.0,
        "order_date": "2026-08-20 10:00:00",
        "status": "completed",
    }])
    razorpay_df_bad_fee = pd.DataFrame([{
        "order_id": "ORD_FEE",
        "payment_id": "pay_FEE",
        "settlement_id": "setl_001",
        "amount": 1000.0,
        "fee": 50.0,  # 5% instead of 2%
        "tax": 9.0,
        "net_amount": 941.0,
        "payment_date": "2026-08-20 10:01:00",
        "settlement_date": "2026-08-21",
        "status": "captured",
    }])
    _, anomalies_fee, _, _ = run_phase1(merchant_df, razorpay_df_bad_fee)
    assert len(anomalies_fee) == 1
    assert anomalies_fee[0]["anomaly_type"] == "FEE_DISCREPANCY"

    # Test abnormal GST tax with standard fee: the net is short, so under the
    # check ordering (fee rate → net/refund → tax) this is a PARTIAL_REFUND —
    # a standard 2% fee plus a reduced net means money was deducted post-fee,
    # even when the tax line itself looks unusual.
    razorpay_df_bad_tax = pd.DataFrame([{
        "order_id": "ORD_FEE",
        "payment_id": "pay_FEE",
        "settlement_id": "setl_001",
        "amount": 1000.0,
        "fee": 20.0,  # standard 2%
        "tax": 15.0,  # should be 3.6
        "net_amount": 965.0,
        "payment_date": "2026-08-20 10:01:00",
        "settlement_date": "2026-08-21",
        "status": "captured",
    }])
    _, anomalies_tax, _, _ = run_phase1(merchant_df, razorpay_df_bad_tax)
    assert len(anomalies_tax) == 1
    assert anomalies_tax[0]["anomaly_type"] == "PARTIAL_REFUND"

    # Test missing GST line: tax=0 inflates the net above expected, so the
    # (short-only) refund check is skipped and this stays FEE_DISCREPANCY.
    razorpay_df_no_tax = pd.DataFrame([{
        "order_id": "ORD_FEE",
        "payment_id": "pay_FEE",
        "settlement_id": "setl_001",
        "amount": 1000.0,
        "fee": 20.0,  # standard 2%
        "tax": 0.0,  # missing GST line
        "net_amount": 980.0,
        "payment_date": "2026-08-20 10:01:00",
        "settlement_date": "2026-08-21",
        "status": "captured",
    }])
    _, anomalies_no_tax, _, _ = run_phase1(merchant_df, razorpay_df_no_tax)
    assert len(anomalies_no_tax) == 1
    assert anomalies_no_tax[0]["anomaly_type"] == "FEE_DISCREPANCY"



def test_phase1_partial_refund():
    merchant_df = pd.DataFrame([{
        "order_id": "ORD_REFUND",
        "amount": 1000.0,
        "order_date": "2026-08-20 10:00:00",
        "status": "completed",
    }])
    # Normal fee (20) & tax (3.60), but net is reduced by 200 (refund)
    razorpay_df = pd.DataFrame([{
        "order_id": "ORD_REFUND",
        "payment_id": "pay_REFUND",
        "settlement_id": "setl_001",
        "amount": 1000.0,
        "fee": 20.0,
        "tax": 3.6,
        "net_amount": 776.4,  # Expected was 976.4
        "payment_date": "2026-08-20 10:01:00",
        "settlement_date": "2026-08-21",
        "status": "captured",
    }])
    _, anomalies, _, _ = run_phase1(merchant_df, razorpay_df)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "PARTIAL_REFUND"


# ─── Settlement Matcher Tests (Phase 2) ──────────────────────────────────────

def test_phase2_batch_match():
    razorpay_df = pd.DataFrame([
        {
            "order_id": "ORD_01",
            "payment_id": "pay_01",
            "settlement_id": "setl_100",
            "amount": 1000.0,
            "net_amount": 976.4,
            "settlement_date": "2026-08-21",
        },
        {
            "order_id": "ORD_02",
            "payment_id": "pay_02",
            "settlement_id": "setl_100",
            "amount": 2000.0,
            "net_amount": 1952.8,
            "settlement_date": "2026-08-21",
        },
    ])
    total_net = 976.4 + 1952.8  # 2929.20
    bank_df = pd.DataFrame([{
        "utr_number": "UTR_TEST_100",
        "deposit_amount": total_net,
        "deposit_date": "2026-08-21",
        "description": "RAZORPAY SETTLEMENT setl_100",
    }])

    p2_matches, p2_anomalies, unmatched_bank = run_phase2(razorpay_df, bank_df, [])
    assert len(p2_matches) == 1
    assert p2_matches[0]["settlement_id"] == "setl_100"
    assert p2_matches[0]["utr_number"] == "UTR_TEST_100"
    assert len(unmatched_bank) == 0


# ─── Graph Matcher Tests (Phase 3: Bounded Subset-Sum) ───────────────────────

def test_phase3_subset_sum():
    # 2 razorpay nets summing to 1 bank deposit
    unmatched_nets_multi = [
        {"id": "setl_1", "settlement_id": "setl_1", "net_amount": 3000.0, "settlement_date": "2026-08-20"},
        {"id": "setl_2", "settlement_id": "setl_2", "net_amount": 2000.0, "settlement_date": "2026-08-20"},
    ]
    unmatched_bank_single = [{
        "utr_number": "UTR_COMBINED",
        "deposit_amount": 5000.0,
        "deposit_date": "2026-08-21",
        "description": "BATCH DEPOSIT",
    }]

    matches, still_unmatched = run_phase3(unmatched_nets_multi, unmatched_bank_single)
    assert len(matches) == 1
    assert matches[0]["matched_total"] == 5000.0
    assert matches[0]["bank_utr"] == "UTR_COMBINED"
    assert len(matches[0]["matched_settlements"]) == 2


def test_phase3_prune_candidates_decimal():
    """Verify that _prune_candidates handles Decimal targets and candidates (>15 items) without TypeError."""
    from decimal import Decimal
    # Create 20 unmatched nets (> MAX_CANDIDATES = 15) with Decimal net amounts
    unmatched_nets = [
        {
            "id": f"setl_{i}",
            "settlement_id": f"setl_{i}",
            "net_amount": Decimal(f"{1000 + i * 50}.00"),
            "settlement_date": "2026-08-20",
        }
        for i in range(20)
    ]
    unmatched_bank = [{
        "utr_number": "UTR_TEST_PRUNE",
        "deposit_amount": Decimal("2050.00"),  # setl_0 (1000) + setl_1 (1050)
        "deposit_date": "2026-08-20",
        "description": "BATCH DEPOSIT",
    }]

    matches, still_unmatched = run_phase3(unmatched_nets, unmatched_bank)
    assert len(matches) == 1
    assert matches[0]["matched_total"] == Decimal("2050.00")
    assert matches[0]["bank_utr"] == "UTR_TEST_PRUNE"


# ─── Scorer Tests (Phase 5) ──────────────────────────────────────────────────

def test_scorer_accuracy():
    anomalies = [
        {
            "order_id": "ORD_1",
            "anomaly_type": "TIMING_MISMATCH",
            "ai_classification": "TIMING_MISMATCH",
            "ai_confidence": "high",
        },
        {
            "order_id": "ORD_2",
            "anomaly_type": "PARTIAL_REFUND",
            "ai_classification": "PARTIAL_REFUND",
            "ai_confidence": "high",
        },
        {
            "order_id": "ORD_3",
            "anomaly_type": "FEE_DISCREPANCY",
            "ai_classification": "FEE_DISCREPANCY",
            "ai_confidence": "high",
        },
    ]
    ground_truth = pd.DataFrame([
        {"order_id": "ORD_1", "injected_anomaly_type": "TIMING_MISMATCH"},
        {"order_id": "ORD_2", "injected_anomaly_type": "PARTIAL_REFUND"},
        {"order_id": "ORD_3", "injected_anomaly_type": "FEE_DISCREPANCY"},
        {"order_id": "ORD_CLEAN", "injected_anomaly_type": "NONE"},
    ])
    matched_ids = {"ORD_CLEAN"}

    scores = score_results(anomalies, ground_truth, matched_ids)
    assert scores["engine_accuracy"] == 100.0
    assert scores["ai_accuracy"] == 100.0
    assert len(scores["mismatches"]) == 0


# ─── CSV Parser Validation Tests ─────────────────────────────────────────────

def test_csv_validation_missing_column():
    bad_df = pd.DataFrame([{"wrong_col": 123}])
    with pytest.raises(CSVValidationError):
        validate_columns(bad_df, ["order_id", "amount"], "test.csv")


def test_csv_parser_indian_thousands_separator(tmp_path):
    from engine.csv_parser import parse_merchant_orders, parse_bank_statement
    csv_file = tmp_path / "merchant_orders.csv"
    csv_file.write_text(
        "order_id,amount,order_date,status\n"
        "ORD_101,\"1,48,250.00\",2026-08-20,completed\n"
        "ORD_102,\"₹2,499.50\",2026-08-20,completed\n",
        encoding="utf-8"
    )

    df = parse_merchant_orders(str(csv_file))
    assert df["amount"].iloc[0] == 148250.00
    assert df["amount"].iloc[1] == 2499.50
    assert not df["amount"].isna().any()


def test_csv_parser_dayfirst_dates(tmp_path):
    from engine.csv_parser import parse_merchant_orders
    csv_file = tmp_path / "merchant_orders.csv"
    # 03/04/2026 in Indian convention is 3rd April 2026 (day=3, month=4)
    csv_file.write_text(
        "order_id,amount,order_date,status\n"
        "ORD_201,1000.0,03/04/2026,completed\n"
    )
    df = parse_merchant_orders(str(csv_file))
    parsed_date = df["order_date"].iloc[0]
    assert parsed_date.day == 3
    assert parsed_date.month == 4


def test_phase1_duplicate_merchant_order():
    merchant_df = pd.DataFrame([
        {"order_id": "ORD_DUP", "amount": 1000.0, "order_date": "2026-08-20", "status": "completed"},
        {"order_id": "ORD_DUP", "amount": 1000.0, "order_date": "2026-08-20", "status": "completed"},
    ])
    razorpay_df = pd.DataFrame([
        {
            "order_id": "ORD_DUP",
            "payment_id": "pay_dup",
            "amount": 1000.0,
            "fee": 20.0,
            "tax": 3.6,
            "net_amount": 976.4,
            "settlement_id": "setl_dup",
            "payment_date": "2026-08-20",
            "settlement_date": "2026-08-21",
            "status": "captured",
        }
    ])
    _, anomalies, _, _ = run_phase1(merchant_df, razorpay_df)
    dup_anomalies = [a for a in anomalies if a["anomaly_type"] == "DUPLICATE_MERCHANT_ORDER"]
    assert len(dup_anomalies) == 1
    assert dup_anomalies[0]["order_id"] == "ORD_DUP"


def test_settlement_mismatch_fallback():
    from engine.ai_investigator import _fallback_classification
    anomaly = {"order_id": "SETTLEMENT_setl_test", "anomaly_type": "SETTLEMENT_MISMATCH"}
    res = _fallback_classification(anomaly)
    assert res["ai_classification"] == "SETTLEMENT_MISMATCH"
    assert res["needs_manual_review"] is True


def test_ai_cache_fingerprint_invalidation(tmp_path):
    from engine.ai_investigator import save_ai_cache, load_ai_cache
    cache_file = str(tmp_path / "test_cache.json")
    original_anomalies = [{
        "order_id": "ORD_CACHE",
        "anomaly_type": "AMOUNT_MISMATCH",
        "merchant_data": {"amount": 500.0},
        "razorpay_data": {"amount": 600.0},
        "ai_classification": "AMOUNT_DISCREPANCY",
        "ai_explanation": "Original explanation for 500 vs 600",
        "needs_manual_review": True,
    }]
    save_ai_cache(original_anomalies, cache_file)

    # When transaction amounts change, old cached explanation should NOT be returned
    changed_anomalies = [{
        "order_id": "ORD_CACHE",
        "anomaly_type": "AMOUNT_MISMATCH",
        "merchant_data": {"amount": 700.0},  # Amount modified!
        "razorpay_data": {"amount": 800.0},
    }]
    loaded = load_ai_cache(changed_anomalies, cache_file)
    # Cache should miss and fall back to rule-based fallback instead of returning stale explanation
    assert loaded[0]["ai_explanation"] != "Original explanation for 500 vs 600"


def test_end_to_end_decimal_types():
    from decimal import Decimal
    from engine.models import MerchantOrder, RazorpayTransaction, BankDeposit, MatchResult

    order = MerchantOrder(
        order_id="ORD_DEC",
        amount=Decimal("1499.50"),
        order_date="2026-08-20T10:00:00",
        status="completed",
    )
    assert isinstance(order.amount, Decimal)
    assert order.amount == Decimal("1499.50")

    merchant_df = pd.DataFrame([
        {"order_id": "ORD_DEC_1", "amount": 1000.0, "order_date": "2026-08-20", "status": "completed"}
    ])
    razorpay_df = pd.DataFrame([{
        "order_id": "ORD_DEC_1",
        "payment_id": "pay_dec_1",
        "amount": 1000.0,
        "fee": 20.0,
        "tax": 3.6,
        "net_amount": 976.4,
        "settlement_id": "setl_dec",
        "payment_date": "2026-08-20",
        "settlement_date": "2026-08-21",
        "status": "captured",
    }])
    matched, _, _, _ = run_phase1(merchant_df, razorpay_df)
    assert len(matched) == 1
    # Verify outputs are Decimal instances
    assert isinstance(matched[0]["merchant_amount"], Decimal)
    assert isinstance(matched[0]["razorpay_amount"], Decimal)
    assert isinstance(matched[0]["razorpay_net"], Decimal)


