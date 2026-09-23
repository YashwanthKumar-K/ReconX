"""
CSV Parser & Normalizer for ReconX.

Reads the three ledger CSVs into pandas DataFrames with proper types.
"""
import pandas as pd
from pathlib import Path
from typing import Optional


MAX_CSV_ROWS = 100_000


class CSVValidationError(Exception):
    """Raised when an uploaded CSV is missing required columns or has invalid structure."""
    pass


def validate_columns(df: pd.DataFrame, required: list[str], filename: str) -> None:
    if len(df) > MAX_CSV_ROWS:
        raise CSVValidationError(f"'{filename}' exceeds maximum allowed rows ({MAX_CSV_ROWS:,}). Found {len(df):,} rows.")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise CSVValidationError(f"'{filename}' is missing required columns: {', '.join(missing)}")


def _clean_numeric(series: pd.Series) -> pd.Series:
    """Clean monetary strings (stripping Indian commas '1,48,250.00', currency symbols, spaces) into numeric."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def parse_merchant_orders(path: str) -> pd.DataFrame:
    """Parse merchant_orders.csv into a clean DataFrame."""
    df = pd.read_csv(path)
    validate_columns(df, ["order_id", "amount", "order_date", "status"], "merchant_orders.csv")
    df["amount"] = _clean_numeric(df["amount"])
    df["order_date"] = pd.to_datetime(df["order_date"], format="mixed", dayfirst=True)
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    return df


def parse_razorpay_transactions(path: str) -> pd.DataFrame:
    """Parse razorpay_transactions.csv into a clean DataFrame."""
    df = pd.read_csv(path)
    validate_columns(df, ["order_id", "payment_id", "settlement_id", "amount", "fee", "tax", "net_amount", "payment_date", "settlement_date", "status"], "razorpay_transactions.csv")
    for col in ["amount", "fee", "tax", "net_amount"]:
        df[col] = _clean_numeric(df[col])
    df["payment_date"] = pd.to_datetime(df["payment_date"], format="mixed", dayfirst=True)
    df["settlement_date"] = pd.to_datetime(df["settlement_date"], format="mixed", dayfirst=True).dt.date
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["payment_id"] = df["payment_id"].astype(str).str.strip()
    df["settlement_id"] = df["settlement_id"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    return df


def parse_bank_statement(path: str) -> pd.DataFrame:
    """Parse bank_statement.csv into a clean DataFrame."""
    df = pd.read_csv(path)
    validate_columns(df, ["utr_number", "deposit_amount", "deposit_date", "description"], "bank_statement.csv")
    df["deposit_amount"] = _clean_numeric(df["deposit_amount"])
    df["deposit_date"] = pd.to_datetime(df["deposit_date"], format="mixed", dayfirst=True).dt.date
    df["utr_number"] = df["utr_number"].astype(str).str.strip()
    df["description"] = df["description"].astype(str).str.strip()
    return df



def parse_ground_truth(path: str) -> pd.DataFrame:
    """Parse ground_truth.csv — the private answer key."""
    df = pd.read_csv(path)
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["injected_anomaly_type"] = df["injected_anomaly_type"].astype(str).str.strip()
    return df



def load_all_data(data_dir: str) -> dict[str, Optional[pd.DataFrame]]:
    """
    Load CSVs from a directory. ground_truth.csv is optional.

    Returns:
        Dict with keys: merchant, razorpay, bank, ground_truth (None if missing).
    """
    path_obj = Path(data_dir)
    gt_path = path_obj / "ground_truth.csv"
    return {
        "merchant": parse_merchant_orders(str(path_obj / "merchant_orders.csv")),
        "razorpay": parse_razorpay_transactions(str(path_obj / "razorpay_transactions.csv")),
        "bank": parse_bank_statement(str(path_obj / "bank_statement.csv")),
        "ground_truth": parse_ground_truth(str(gt_path)) if gt_path.exists() else None,
    }
