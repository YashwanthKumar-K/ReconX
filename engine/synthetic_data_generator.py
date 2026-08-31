"""
Synthetic Data Generator for ReconX.

Generates realistic Merchant, Razorpay, and Bank CSVs with deliberate anomalies injected.
Also produces a ground_truth.csv (private answer key) for scoring.
"""
import csv
import os
import random
import string
from datetime import datetime, timedelta, date
from typing import Optional


# ─── Configuration ───────────────────────────────────────────────────────────

RAZORPAY_FEE_RATE = 0.02           # 2% processing fee
RAZORPAY_TAX_RATE = 0.18           # 18% GST on fee
ANOMALY_RATIO = 0.10               # ~10% of transactions will have anomalies

PRODUCT_CATALOG = [
    ("Blue T-Shirt", 499.00), ("Running Shoes", 2999.00), ("Wireless Earbuds", 1499.00),
    ("Laptop Stand", 899.00), ("Phone Case", 299.00), ("Backpack", 1799.00),
    ("Water Bottle", 399.00), ("Desk Lamp", 1199.00), ("Notebook Set", 249.00),
    ("USB Cable", 199.00), ("Mouse Pad", 349.00), ("Yoga Mat", 999.00),
    ("Coffee Mug", 449.00), ("Sunglasses", 1599.00), ("Watch Strap", 699.00),
    ("Power Bank", 1299.00), ("Keyboard", 2499.00), ("Webcam", 3499.00),
    ("Monitor Light", 1899.00), ("Standing Desk Mat", 1499.00),
]

CUSTOMER_NAMES = [
    "Rahul Sharma", "Priya Patel", "Amit Kumar", "Sneha Gupta", "Vikram Singh",
    "Ananya Reddy", "Rohit Joshi", "Kavita Nair", "Arjun Mehta", "Deepika Rao",
    "Sanjay Verma", "Meera Iyer", "Karthik Sundaram", "Pooja Desai", "Nikhil Agarwal",
    "Ritu Bansal", "Suresh Pillai", "Anjali Saxena", "Manish Tiwari", "Nandini Choudhury",
    "Gaurav Malhotra", "Shreya Bhat", "Rajesh Menon", "Divya Kulkarni", "Aakash Jain",
]


# ─── Anomaly Types ───────────────────────────────────────────────────────────

ANOMALY_TYPES = [
    "TIMING_MISMATCH",
    "PARTIAL_REFUND",
    "SPLIT_SETTLEMENT",
    "DUPLICATE_PAYMENT",
    "MISSING_RECORD",
    "FEE_DISCREPANCY",
]


def _random_id(prefix: str, length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}{''.join(random.choices(chars, k=length))}"


def generate_data(
    num_orders: int = 50,
    output_dir: str = "data/sample",
    seed: int = 42,
) -> dict:
    """
    Generate synthetic reconciliation data.

    Args:
        num_orders: Number of merchant orders to generate.
        output_dir: Directory to write CSV files.
        seed: Random seed for reproducibility.

    Returns:
        Dict with paths to generated files.
    """
    random.seed(seed)
    os.makedirs(output_dir, exist_ok=True)

    # ─── Decide which orders get anomalies ────────────────────────────────
    num_anomalies = min(num_orders, max(1, int(num_orders * ANOMALY_RATIO)))
    anomaly_indices = set(random.sample(range(num_orders), num_anomalies))

    # Assign anomaly types round-robin so every type appears at least once
    anomaly_assignments = {}
    anomaly_type_list = list(ANOMALY_TYPES)
    for i, idx in enumerate(sorted(anomaly_indices)):
        anomaly_assignments[idx] = anomaly_type_list[i % len(anomaly_type_list)]

    # ─── Generate base data ───────────────────────────────────────────────
    base_date = datetime(2026, 8, 20, 9, 0, 0)
    settlement_counter = 1
    current_settlement_id = f"setl_{settlement_counter:03d}"
    settlement_orders = []  # orders in current settlement batch
    settlement_net_total = 0.0

    merchant_rows = []
    razorpay_rows = []
    bank_rows = []
    ground_truth_rows = []

    # Track settlements for bank statement generation
    settlements = {}  # settlement_id -> {net_total, settlement_date, order_ids}

    for i in range(num_orders):
        order_id = f"ORD_{1001 + i}"
        product, base_price = random.choice(PRODUCT_CATALOG)
        # Add some price variation
        amount = round(base_price + random.uniform(-50, 50), 2)
        amount = max(100, amount)  # minimum ₹100
        customer = random.choice(CUSTOMER_NAMES)

        # Spread orders across ~7 days, with realistic business hours
        day_offset = i * 7 // num_orders
        hour = random.randint(8, 23)
        minute = random.randint(0, 59)
        order_date = base_date + timedelta(days=day_offset, hours=hour, minutes=minute)

        anomaly_type = anomaly_assignments.get(i, "NONE")

        # ─── Merchant row (always created) ────────────────────────────
        merchant_status = "completed"
        if anomaly_type == "PARTIAL_REFUND":
            merchant_status = "completed"  # merchant sees original order as completed
        merchant_rows.append({
            "order_id": order_id,
            "customer_name": customer,
            "amount": amount,
            "order_date": order_date.strftime("%Y-%m-%d %H:%M:%S"),
            "status": merchant_status,
            "product": product,
        })

        # ─── Ground truth ─────────────────────────────────────────────
        ground_truth_rows.append({
            "order_id": order_id,
            "injected_anomaly_type": anomaly_type,
        })

        # ─── Handle anomalies ─────────────────────────────────────────

        # MISSING_RECORD: merchant has order, Razorpay doesn't
        if anomaly_type == "MISSING_RECORD":
            continue  # skip creating Razorpay & bank records for this order

        # Calculate fees
        fee = round(amount * RAZORPAY_FEE_RATE, 2)
        tax = round(fee * RAZORPAY_TAX_RATE, 2)
        net_amount = round(amount - fee - tax, 2)

        # Razorpay payment date is slightly after order date
        payment_date = order_date + timedelta(minutes=random.randint(1, 5))

        # Settlement date is next business day
        settlement_date = (order_date + timedelta(days=1)).date()

        razorpay_status = "captured"
        actual_net = net_amount  # what actually gets settled

        if anomaly_type == "TIMING_MISMATCH":
            # Payment at 11:58-11:59 PM — crosses midnight
            payment_date = order_date.replace(hour=23, minute=random.choice([58, 59]))
            order_date_adjusted = order_date.replace(hour=23, minute=payment_date.minute - 1)
            merchant_rows[-1]["order_date"] = order_date_adjusted.strftime("%Y-%m-%d %H:%M:%S")
            # Settlement date shifts to day after next
            settlement_date = (order_date + timedelta(days=2)).date()

        elif anomaly_type == "PARTIAL_REFUND":
            # Partial refund: ₹200 refunded, net is less
            refund_amount = round(min(200, amount * 0.2), 2)
            actual_net = round(net_amount - refund_amount, 2)
            razorpay_status = "captured"  # original status stays captured
            # Razorpay records the original amount but net is reduced

        elif anomaly_type == "FEE_DISCREPANCY":
            # Fee is 2.36% instead of 2% (changed rate)
            fee = round(amount * 0.0236, 2)
            tax = round(fee * RAZORPAY_TAX_RATE, 2)
            net_amount = round(amount - fee - tax, 2)
            actual_net = net_amount

        elif anomaly_type == "DUPLICATE_PAYMENT":
            # Create a duplicate Razorpay transaction
            dup_payment_id = _random_id("pay_")
            dup_payment_date = payment_date + timedelta(seconds=30)
            razorpay_rows.append({
                "payment_id": dup_payment_id,
                "order_id": order_id,
                "amount": amount,
                "fee": fee,
                "tax": tax,
                "net_amount": net_amount,
                "settlement_id": current_settlement_id,
                "payment_date": dup_payment_date.strftime("%Y-%m-%d %H:%M:%S"),
                "settlement_date": settlement_date.isoformat(),
                "status": "captured",
            })
            # The duplicate's net also goes into the settlement
            if current_settlement_id not in settlements:
                settlements[current_settlement_id] = {
                    "net_total": 0, "settlement_date": settlement_date, "order_ids": []
                }
            settlements[current_settlement_id]["net_total"] += net_amount
            settlements[current_settlement_id]["order_ids"].append(f"{order_id}_DUP")

        # ─── Create Razorpay transaction ──────────────────────────────
        payment_id = _random_id("pay_")

        # For PARTIAL_REFUND, store original net but actual settlement is less
        razorpay_row_net = net_amount
        if anomaly_type == "PARTIAL_REFUND":
            razorpay_row_net = actual_net  # Razorpay shows adjusted net

        razorpay_rows.append({
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "net_amount": razorpay_row_net,
            "settlement_id": current_settlement_id,
            "payment_date": payment_date.strftime("%Y-%m-%d %H:%M:%S"),
            "settlement_date": settlement_date.isoformat(),
            "status": razorpay_status,
        })

        # ─── Accumulate into settlement ───────────────────────────────
        if current_settlement_id not in settlements:
            settlements[current_settlement_id] = {
                "net_total": 0, "settlement_date": settlement_date, "order_ids": []
            }
        settlements[current_settlement_id]["net_total"] += razorpay_row_net
        settlements[current_settlement_id]["order_ids"].append(order_id)

        # Start new settlement batch every ~8-12 orders
        settlement_orders.append(order_id)
        batch_size = random.randint(8, 12)
        if len(settlement_orders) >= batch_size:
            settlement_counter += 1
            current_settlement_id = f"setl_{settlement_counter:03d}"
            settlement_orders = []

    # ─── Generate Bank Statement from settlements ─────────────────────────
    split_settlement_id = None
    actually_split_orders = set()  # Track orders where the split actually happened

    for setl_id, setl_data in settlements.items():
        net_total = round(setl_data["net_total"], 2)
        setl_date = setl_data["settlement_date"]

        # Check if any order in this settlement is a SPLIT_SETTLEMENT anomaly
        has_split = False
        for oid in setl_data["order_ids"]:
            for gt in ground_truth_rows:
                if gt["order_id"] == oid and gt["injected_anomaly_type"] == "SPLIT_SETTLEMENT":
                    has_split = True
                    split_settlement_id = setl_id
                    break

        if has_split and net_total > 1000:
            # Only split if amount is large enough — and record which orders this affects
            split_amount = round(net_total * 0.6, 2)
            remainder = round(net_total - split_amount, 2)

            bank_rows.append({
                "utr_number": _random_id("UTR"),
                "deposit_amount": split_amount,
                "deposit_date": setl_date.isoformat(),
                "description": f"RAZORPAY SETTLEMENT {setl_id} PART1",
                "bank_ref": _random_id("REF_"),
            })
            bank_rows.append({
                "utr_number": _random_id("UTR"),
                "deposit_amount": remainder,
                "deposit_date": (setl_date + timedelta(days=1)).isoformat(),
                "description": f"RAZORPAY SETTLEMENT {setl_id} PART2",
                "bank_ref": _random_id("REF_"),
            })
            # Record which orders were truly split so ground truth stays accurate
            for oid in setl_data["order_ids"]:
                actually_split_orders.add(oid)
        else:
            bank_rows.append({
                "utr_number": _random_id("UTR"),
                "deposit_amount": net_total,
                "deposit_date": setl_date.isoformat(),
                "description": f"RAZORPAY SETTLEMENT {setl_id}",
                "bank_ref": _random_id("REF_"),
            })

    # Fix up ground truth: reclassify SPLIT_SETTLEMENT to NONE if no split actually happened
    for gt in ground_truth_rows:
        if gt["injected_anomaly_type"] == "SPLIT_SETTLEMENT" and gt["order_id"] not in actually_split_orders:
            gt["injected_anomaly_type"] = "NONE"


    # ─── Write CSVs ───────────────────────────────────────────────────────

    def write_csv(filename, rows, fieldnames):
        path = os.path.join(output_dir, filename)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    paths = {}

    paths["merchant"] = write_csv(
        "merchant_orders.csv", merchant_rows,
        ["order_id", "customer_name", "amount", "order_date", "status", "product"]
    )

    paths["razorpay"] = write_csv(
        "razorpay_transactions.csv", razorpay_rows,
        ["payment_id", "order_id", "amount", "fee", "tax", "net_amount",
         "settlement_id", "payment_date", "settlement_date", "status"]
    )

    paths["bank"] = write_csv(
        "bank_statement.csv", bank_rows,
        ["utr_number", "deposit_amount", "deposit_date", "description", "bank_ref"]
    )

    paths["ground_truth"] = write_csv(
        "ground_truth.csv", ground_truth_rows,
        ["order_id", "injected_anomaly_type"]
    )

    # ─── Summary ──────────────────────────────────────────────────────────
    anomaly_counts = {}
    for gt in ground_truth_rows:
        t = gt["injected_anomaly_type"]
        anomaly_counts[t] = anomaly_counts.get(t, 0) + 1

    summary = {
        "total_orders": len(merchant_rows),
        "total_razorpay_txns": len(razorpay_rows),
        "total_bank_deposits": len(bank_rows),
        "total_settlements": len(settlements),
        "anomaly_counts": anomaly_counts,
        "paths": paths,
    }

    return summary


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    num = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    output = sys.argv[2] if len(sys.argv) > 2 else "data/sample"

    print(f"[*] Generating {num} orders...")
    result = generate_data(num_orders=num, output_dir=output)

    print(f"\n[OK] Generated data:")
    print(f"   Merchant orders:       {result['total_orders']}")
    print(f"   Razorpay transactions: {result['total_razorpay_txns']}")
    print(f"   Bank deposits:         {result['total_bank_deposits']}")
    print(f"   Settlements:           {result['total_settlements']}")
    print(f"\n[STATS] Anomaly breakdown:")
    for atype, count in result["anomaly_counts"].items():
        print(f"   {atype}: {count}")
    print(f"\n[FILES] Written to: {output}")
