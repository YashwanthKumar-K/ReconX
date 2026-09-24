"""
Phase 1: Direct Key Matching (Merchant ↔ Razorpay)

Matches merchant orders to Razorpay transactions using order_id as the key.
Also handles fee-rate discrepancy detection deterministically.
Uses Python Decimal for all monetary comparisons to avoid binary float drift.
"""
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Tuple

from engine.config import config

# Razorpay gateway payment statuses that represent no money movement.
# Orders/payments in these states must NOT be reconciled as settled.
TERMINAL_STATUSES = frozenset({"failed", "refunded", "reversed", "expired"})


def _d(value) -> Decimal:
    """Convert a numeric value to Decimal with 2 decimal places (INR paise precision)."""
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return Decimal("0.00")


def run_phase1(
    merchant_df: pd.DataFrame,
    razorpay_df: pd.DataFrame,
) -> Tuple[list[dict], list[dict], pd.DataFrame, pd.DataFrame]:
    """
    Phase 1: Direct key matching using order_id.

    Returns:
        matched: list of matched result dicts
        anomalies: list of anomaly dicts
        unmatched_merchant: DataFrame of merchant orders not matched
        unmatched_razorpay: DataFrame of Razorpay txns not matched
    """
    matched = []
    anomalies = []

    # Index Razorpay transactions by order_id
    # Handle duplicates: group by order_id
    rz_by_order = {}
    for idx, row in razorpay_df.iterrows():
        oid = row["order_id"]
        if oid not in rz_by_order:
            rz_by_order[oid] = []
        rz_by_order[oid].append(row)

    matched_merchant_ids = set()
    matched_razorpay_ids = set()
    seen_merchant_order_ids = set()

    for _, m_row in merchant_df.iterrows():
        order_id = m_row["order_id"]

        # Duplicate merchant order detection
        if order_id in seen_merchant_order_ids:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "DUPLICATE_MERCHANT_ORDER",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row.get("status", ""),
                    "product": m_row.get("product", ""),
                    "customer_name": m_row.get("customer_name", ""),
                },
                "razorpay_data": None,
                "note": f"Duplicate merchant order: order_id {order_id} appears more than once in merchant ledger.",
            })
            continue
        seen_merchant_order_ids.add(order_id)

        if order_id not in rz_by_order:
            # Missing in Razorpay

            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "MISSING_RECORD",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row.get("status", ""),
                    "product": m_row.get("product", ""),
                    "customer_name": m_row.get("customer_name", ""),
                },
                "razorpay_data": None,
                "note": f"Order {order_id} exists in merchant records but not in Razorpay.",
            })
            matched_merchant_ids.add(order_id)
            continue

        # ── Status-aware matching ──────────────────────────────────────────
        # A merchant order in a terminal state (failed/refunded/etc.) should
        # not silently pass as a clean reconciliation.  Flag it immediately.
        m_status = str(m_row.get("status", "")).strip().lower()
        if m_status in TERMINAL_STATUSES:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "FAILED_ORDER",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row.get("status", ""),
                    "product": m_row.get("product", ""),
                    "customer_name": m_row.get("customer_name", ""),
                },
                "razorpay_data": None,
                "note": (
                    f"Order {order_id} has terminal status '{m_row.get('status', '')}' "
                    f"in the merchant ledger — no money settled; skip reconciliation."
                ),
            })
            matched_merchant_ids.add(order_id)
            continue



        rz_list = rz_by_order[order_id]

        # Check for duplicate payments
        if len(rz_list) > 1:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "DUPLICATE_PAYMENT",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row.get("status", ""),
                    "product": m_row.get("product", ""),
                    "customer_name": m_row.get("customer_name", ""),
                },
                "razorpay_data": [
                    {
                        "payment_id": r["payment_id"],
                        "amount": _d(r["amount"]),
                        "fee": _d(r["fee"]),
                        "net_amount": _d(r["net_amount"]),
                        "payment_date": str(r["payment_date"]),
                    }
                    for r in rz_list
                ],
                "note": f"Order {order_id} has {len(rz_list)} Razorpay transactions (expected 1).",
            })
            matched_merchant_ids.add(order_id)
            for r in rz_list:
                matched_razorpay_ids.add(r["payment_id"])
            continue

        rz_row = rz_list[0]

        import pandas as _pd
        # Data corruption check (NaN propagation bug fix)
        if _pd.isna(m_row["amount"]) or _pd.isna(rz_row["amount"]) or _pd.isna(rz_row["fee"]) or _pd.isna(rz_row["net_amount"]):
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "REQUIRES_MANUAL_REVIEW",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": "NaN/Corrupt" if _pd.isna(m_row["amount"]) else _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": "NaN/Corrupt" if _pd.isna(rz_row["amount"]) else _d(rz_row["amount"]),
                    "fee": "NaN/Corrupt" if _pd.isna(rz_row["fee"]) else _d(rz_row["fee"]),
                    "net_amount": "NaN/Corrupt" if _pd.isna(rz_row["net_amount"]) else _d(rz_row["net_amount"]),
                },
                "note": "Corrupt or non-numeric data detected (NaN values). Cannot safely process.",
            })
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue


        # ── Gateway payment status check ──────────────────────────────────
        # A Razorpay payment that failed or was refunded should not count as
        # settled — flag it so the analyst knows money never moved.
        rz_status = str(rz_row.get("status", "")).strip().lower()
        if rz_status in TERMINAL_STATUSES:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "FAILED_PAYMENT",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row.get("status", ""),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": _d(rz_row["amount"]),
                    "status": rz_row.get("status", ""),
                    "payment_date": str(rz_row["payment_date"]),
                },
                "note": (
                    f"Razorpay payment {rz_row['payment_id']} has status "
                    f"'{rz_row.get('status', '')}' — funds were not captured. "
                    f"Do not count as settled."
                ),
            })
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # ── Amount check (Decimal, ROUND_HALF_UP) ─────────────────────────
        m_amount = _d(m_row["amount"])
        rz_amount = _d(rz_row["amount"])
        amount_tolerance = _d(config.amount_tolerance)
        amount_match = abs(m_amount - rz_amount) < amount_tolerance

        if not amount_match:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "AMOUNT_MISMATCH",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": m_amount,
                    "order_date": str(m_row["order_date"]),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": rz_amount,
                    "payment_date": str(rz_row["payment_date"]),
                },
                "note": f"Merchant amount ₹{m_row['amount']} ≠ Razorpay amount ₹{rz_row['amount']}.",
            })
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # ── Fee & tax check (Decimal — MDR 2% + GST 18% on fee) ──────────
        # ── Fee / tax values (Decimal — MDR 2% + GST 18% on fee) ─────────
        actual_fee = _d(rz_row["fee"])
        # tax=0 is NOT treated as a pass — it means a missing GST line (bug fix)
        raw_tax = rz_row.get("tax", None)
        tax_present = raw_tax is not None and not (_pd.isna(raw_tax) if hasattr(_pd, 'isna') else False)
        actual_tax = _d(raw_tax) if tax_present else None

        actual_fee_rate = float(actual_fee) / float(rz_amount) if float(rz_amount) > 0 else 0.0
        expected_fee = (rz_amount * _d(config.expected_fee_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # GST threshold scales with order amount: max(₹0.50, 5% of expected tax) → never ±122% on small orders
        expected_tax = (expected_fee * _d("0.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax_abs_threshold = max(_d("0.50"), (expected_tax * _d("0.05")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        fee_rate_discrepancy = abs(actual_fee_rate - config.expected_fee_rate) > config.fee_rate_tolerance
        if actual_tax is None:
            # Missing GST line entirely — flag as discrepancy
            tax_discrepancy = True
            tax_missing = True
        else:
            tax_discrepancy = abs(actual_tax - expected_tax) > tax_abs_threshold
            tax_missing = (actual_tax == _d("0.00"))

        # ── Check 1: fee rate ────────────────────────────────────────────
        # If the gateway charged the wrong MDR, the net-vs-standard-formula
        # comparison is meaningless, so this stays FEE_DISCREPANCY and the
        # refund check below is skipped.
        if fee_rate_discrepancy:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "FEE_DISCREPANCY",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": m_amount,
                    "order_date": str(m_row["order_date"]),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": rz_amount,
                    "fee": actual_fee,
                    "tax": actual_tax if actual_tax is not None else None,
                    "net_amount": _d(rz_row["net_amount"]),
                    "config.expected_fee_rate": config.expected_fee_rate,
                    "actual_fee_rate": round(actual_fee_rate, 4),
                },
                "note": (
                    f"Fee rate discrepancy: expected ~{config.expected_fee_rate*100:.1f}%, "
                    f"actual {actual_fee_rate*100:.2f}% "
                    f"(₹{actual_fee} on ₹{rz_amount}). "
                    f"This is a deterministic detection — no AI needed."
                ),
            })
            # Still mark as matched (fee discrepancy is noted, not unmatched)
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # ── Check 2: partial refund / net (Decimal, unified formula) ─────
        # Runs BEFORE the tax check: when the MDR fee is standard (2%) but
        # the net amount is short, money was deducted after fees — a partial
        # refund — even if the tax line itself looks unusual. (Previously the
        # tax check ran first and mislabeled such orders FEE_DISCREPANCY,
        # and its `continue` skipped this check entirely.)
        # Single definition: expected_net = amount × (1 − fee_rate × 1.18)
        fee_factor = _d(config.expected_fee_rate) * _d("1.18")
        expected_net = (m_amount * (Decimal("1") - fee_factor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        actual_net = _d(rz_row["net_amount"])
        # Directional: only a SHORT net indicates a refund. A net HIGHER than
        # expected (e.g. missing/zero GST inflates the net) falls through to
        # the tax check below, preserving missing-GST → FEE_DISCREPANCY.
        net_short = expected_net - actual_net

        if net_short > _d("1.00"):  # net more than ₹1 below expected
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "PARTIAL_REFUND",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": m_amount,
                    "order_date": str(m_row["order_date"]),
                    "status": m_row.get("status", ""),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": rz_amount,
                    "fee": actual_fee,
                    "net_amount": actual_net,
                    "expected_net": expected_net,
                    "difference": net_short,
                    "settlement_id": rz_row["settlement_id"],
                    "payment_date": str(rz_row["payment_date"]),
                },
                "note": (
                    f"Net amount ₹{actual_net} is ₹{net_short} less than expected ₹{expected_net}. "
                    f"Possible partial refund."
                ),
            })
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # ── Check 3: tax ─────────────────────────────────────────────────
        # Reached only with a standard fee rate AND a consistent net amount:
        # a deviant or missing tax line here is a genuine tax discrepancy,
        # not a refund.
        if tax_discrepancy:
            if tax_missing:
                fee_note = (
                    f"Missing GST: expected ₹{expected_tax} (18% on ₹{actual_fee}), "
                    f"actual tax is zero/absent. This is a deterministic detection — no AI needed."
                )
            else:
                fee_note = (
                    f"GST Tax discrepancy: expected GST ~₹{expected_tax} (18% on ₹{actual_fee}), "
                    f"actual GST ₹{actual_tax}. MDR rate is normal ({actual_fee_rate*100:.1f}%), "
                    f"but tax calculation deviates. This is a deterministic detection — no AI needed."
                )
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "FEE_DISCREPANCY",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": m_amount,
                    "order_date": str(m_row["order_date"]),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": rz_amount,
                    "fee": actual_fee,
                    "tax": actual_tax if actual_tax is not None else None,
                    "net_amount": _d(rz_row["net_amount"]),
                    "config.expected_fee_rate": config.expected_fee_rate,
                    "actual_fee_rate": round(actual_fee_rate, 4),
                },
                "note": fee_note,
            })
            # Still mark as matched (fee discrepancy is noted, not unmatched)
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue


        # Check for timing mismatch: order date and payment date on different days,
        # OR late-night order (after 11 PM) where settlement shifts by an extra day
        import pandas as _pd
        order_dt = _pd.Timestamp(m_row["order_date"])
        payment_dt = _pd.Timestamp(rz_row["payment_date"])

        is_cross_day = order_dt.date() != payment_dt.date()
        is_late_night = order_dt.hour >= 23  # 11 PM or later

        # Check if settlement date is further than expected (normal = +1 day)
        expected_settle = (order_dt + _pd.Timedelta(days=1)).date()
        actual_settle = rz_row["settlement_date"]
        if isinstance(actual_settle, str):
            from datetime import date as dt_date
            actual_settle = dt_date.fromisoformat(actual_settle)
        settle_delayed = actual_settle > expected_settle if actual_settle and expected_settle else False

        if is_cross_day or (is_late_night and settle_delayed):
            reason = ""
            if is_cross_day:
                reason = (
                    f"Order placed on {order_dt.date()} but payment captured on {payment_dt.date()}. "
                    f"Midnight cutoff -- order at {order_dt.strftime('%H:%M')}, "
                    f"payment at {payment_dt.strftime('%H:%M')}."
                )
            else:
                reason = (
                    f"Late-night order at {order_dt.strftime('%H:%M')} on {order_dt.date()}. "
                    f"Settlement expected on {expected_settle} but actually on {actual_settle}. "
                    f"Likely missed the settlement cutoff window."
                )

            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "TIMING_MISMATCH",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": _d(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "order_date_only": str(order_dt.date()),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": _d(rz_row["amount"]),
                    "payment_date": str(rz_row["payment_date"]),
                    "payment_date_only": str(payment_dt.date()),
                    "settlement_id": rz_row["settlement_id"],
                    "settlement_date": str(rz_row["settlement_date"]),
                },
                "note": reason,
            })
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # Clean match
        matched.append({
            "order_id": order_id,
            "merchant_amount": _d(m_row["amount"]),
            "razorpay_amount": _d(rz_row["amount"]),
            "razorpay_net": _d(rz_row["net_amount"]),
            "settlement_id": rz_row["settlement_id"],
            "payment_id": rz_row["payment_id"],
            "status": "matched",
            "phase": "Phase 1: Direct Key Matching",
        })
        matched_merchant_ids.add(order_id)
        matched_razorpay_ids.add(rz_row["payment_id"])

    # Find Razorpay transactions not linked to any merchant order
    for _, rz_row in razorpay_df.iterrows():
        if rz_row["payment_id"] not in matched_razorpay_ids:
            if rz_row["order_id"] not in matched_merchant_ids:
                anomalies.append({
                    "order_id": rz_row["order_id"],
                    "anomaly_type": "MISSING_IN_MERCHANT",
                    "detected_in_phase": "Phase 1: Direct Key Matching",
                    "merchant_data": None,
                    "razorpay_data": {
                        "payment_id": rz_row["payment_id"],
                        "amount": _d(rz_row["amount"]),
                        "net_amount": _d(rz_row["net_amount"]),
                        "payment_date": str(rz_row["payment_date"]),
                    },
                    "note": f"Razorpay payment {rz_row['payment_id']} has no matching merchant order.",
                })

    # Build unmatched DataFrames
    unmatched_merchant = merchant_df[~merchant_df["order_id"].isin(matched_merchant_ids)].copy()
    unmatched_razorpay = razorpay_df[~razorpay_df["payment_id"].isin(matched_razorpay_ids)].copy()

    return matched, anomalies, unmatched_merchant, unmatched_razorpay

