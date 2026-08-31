"""
CSV Parser & Normalizer for ReconX.

Reads the three ledger CSVs into pandas DataFrames with proper types.
"""
import pandas as pd
from pathlib import Path
from typing import Optional


def parse_merchant_orders(path: str) -> pd.DataFrame:
    """Parse merchant_orders.csv into a clean DataFrame."""
    df = pd.read_csv(path)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    return df


def parse_razorpay_transactions(path: str) -> pd.DataFrame:
    """Parse razorpay_transactions.csv into a clean DataFrame."""
    df = pd.read_csv(path)
    for col in ["amount", "fee", "tax", "net_amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["payment_date"] = pd.to_datetime(df["payment_date"])
    df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.date
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["payment_id"] = df["payment_id"].astype(str).str.strip()
    df["settlement_id"] = df["settlement_id"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    return df


def parse_bank_statement(path: str) -> pd.DataFrame:
    """Parse bank_statement.csv into a clean DataFrame."""
    df = pd.read_csv(path)
    df["deposit_amount"] = pd.to_numeric(df["deposit_amount"], errors="coerce")
    df["deposit_date"] = pd.to_datetime(df["deposit_date"]).dt.date
    df["utr_number"] = df["utr_number"].astype(str).str.strip()
    df["description"] = df["description"].astype(str).str.strip()
    return df


def parse_ground_truth(path: str) -> pd.DataFrame:
    """Parse ground_truth.csv — the private answer key."""
    df = pd.read_csv(path)
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["injected_anomaly_type"] = df["injected_anomaly_type"].astype(str).str.strip()
    return df


def load_all_data(data_dir: str) -> dict:
    """
    Load CSVs from a directory. ground_truth.csv is optional.

    Returns:
        Dict with keys: merchant, razorpay, bank, ground_truth (None if missing).
    """
    data_dir = Path(data_dir)
    gt_path = data_dir / "ground_truth.csv"
    return {
        "merchant": parse_merchant_orders(str(data_dir / "merchant_orders.csv")),
        "razorpay": parse_razorpay_transactions(str(data_dir / "razorpay_transactions.csv")),
        "bank": parse_bank_statement(str(data_dir / "bank_statement.csv")),
        "ground_truth": parse_ground_truth(str(gt_path)) if gt_path.exists() else None,
    }
