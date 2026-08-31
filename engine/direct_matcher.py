"""
Phase 1: Direct Key Matching (Merchant ↔ Razorpay)

Matches merchant orders to Razorpay transactions using order_id as the key.
Also handles fee-rate discrepancy detection deterministically.
"""
import pandas as pd
from typing import Tuple

# Expected fee rate and tolerance
EXPECTED_FEE_RATE = 0.02  # 2%
FEE_RATE_TOLERANCE = 0.003  # ±0.3% is acceptable
AMOUNT_TOLERANCE = 0.01  # ₹0.01 for floating point


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

    for _, m_row in merchant_df.iterrows():
        order_id = m_row["order_id"]

        if order_id not in rz_by_order:
            # Missing in Razorpay
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "MISSING_RECORD",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": float(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row["status"],
                    "product": m_row["product"],
                    "customer_name": m_row["customer_name"],
                },
                "razorpay_data": None,
                "note": f"Order {order_id} exists in merchant records but not in Razorpay.",
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
                    "amount": float(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row["status"],
                    "product": m_row["product"],
                    "customer_name": m_row["customer_name"],
                },
                "razorpay_data": [
                    {
                        "payment_id": r["payment_id"],
                        "amount": float(r["amount"]),
                        "fee": float(r["fee"]),
                        "net_amount": float(r["net_amount"]),
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

        # Amount check
        amount_match = abs(float(m_row["amount"]) - float(rz_row["amount"])) < AMOUNT_TOLERANCE

        if not amount_match:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "AMOUNT_MISMATCH",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": float(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": float(rz_row["amount"]),
                    "payment_date": str(rz_row["payment_date"]),
                },
                "note": f"Merchant amount ₹{m_row['amount']} ≠ Razorpay amount ₹{rz_row['amount']}.",
            })
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # Fee rate check (deterministic — NOT sent to AI)
        actual_fee_rate = float(rz_row["fee"]) / float(rz_row["amount"]) if float(rz_row["amount"]) > 0 else 0
        fee_note = None
        fee_anomaly = False

        if abs(actual_fee_rate - EXPECTED_FEE_RATE) > FEE_RATE_TOLERANCE:
            fee_anomaly = True
            fee_note = (
                f"Fee rate discrepancy: expected ~{EXPECTED_FEE_RATE*100:.1f}%, "
                f"actual {actual_fee_rate*100:.2f}% "
                f"(₹{rz_row['fee']} on ₹{rz_row['amount']}). "
                f"This is a deterministic detection — no AI needed."
            )

        if fee_anomaly:
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "FEE_DISCREPANCY",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": float(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": float(rz_row["amount"]),
                    "fee": float(rz_row["fee"]),
                    "tax": float(rz_row["tax"]),
                    "net_amount": float(rz_row["net_amount"]),
                    "expected_fee_rate": EXPECTED_FEE_RATE,
                    "actual_fee_rate": round(actual_fee_rate, 4),
                },
                "note": fee_note,
            })
            # Still mark as matched (fee discrepancy is noted, not unmatched)
            matched_merchant_ids.add(order_id)
            matched_razorpay_ids.add(rz_row["payment_id"])
            continue

        # Check for partial refund: merchant amount matches but net is suspiciously low
        expected_net = round(float(m_row["amount"]) * (1 - EXPECTED_FEE_RATE * (1 + 0.18)), 2)
        actual_net = float(rz_row["net_amount"])
        net_diff = abs(expected_net - actual_net)

        if net_diff > 1.0:  # more than ₹1 difference in net
            anomalies.append({
                "order_id": order_id,
                "anomaly_type": "PARTIAL_REFUND",
                "detected_in_phase": "Phase 1: Direct Key Matching",
                "merchant_data": {
                    "amount": float(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "status": m_row["status"],
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": float(rz_row["amount"]),
                    "fee": float(rz_row["fee"]),
                    "net_amount": actual_net,
                    "expected_net": expected_net,
                    "difference": round(net_diff, 2),
                    "settlement_id": rz_row["settlement_id"],
                    "payment_date": str(rz_row["payment_date"]),
                },
                "note": (
                    f"Net amount ₹{actual_net} is ₹{round(net_diff, 2)} less than expected ₹{expected_net}. "
                    f"Possible partial refund."
                ),
            })
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
                    "amount": float(m_row["amount"]),
                    "order_date": str(m_row["order_date"]),
                    "order_date_only": str(order_dt.date()),
                },
                "razorpay_data": {
                    "payment_id": rz_row["payment_id"],
                    "amount": float(rz_row["amount"]),
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
            "merchant_amount": float(m_row["amount"]),
            "razorpay_amount": float(rz_row["amount"]),
            "razorpay_net": float(rz_row["net_amount"]),
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
                        "amount": float(rz_row["amount"]),
                        "net_amount": float(rz_row["net_amount"]),
                        "payment_date": str(rz_row["payment_date"]),
                    },
                    "note": f"Razorpay payment {rz_row['payment_id']} has no matching merchant order.",
                })

    # Build unmatched DataFrames
    unmatched_merchant = merchant_df[~merchant_df["order_id"].isin(matched_merchant_ids)].copy()
    unmatched_razorpay = razorpay_df[~razorpay_df["payment_id"].isin(matched_razorpay_ids)].copy()

    return matched, anomalies, unmatched_merchant, unmatched_razorpay
