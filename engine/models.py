"""
Data models and enums for the ReconX reconciliation engine.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, date


# ─── Enums ───────────────────────────────────────────────────────────────────

class OrderStatus(str, Enum):
    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentStatus(str, Enum):
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


class MatchStatus(str, Enum):
    MATCHED = "matched"
    MATCHED_WITH_NOTE = "matched_with_note"
    ANOMALY = "anomaly"
    UNMATCHED = "unmatched"


class AnomalyType(str, Enum):
    NONE = "NONE"
    TIMING_MISMATCH = "TIMING_MISMATCH"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    SPLIT_SETTLEMENT = "SPLIT_SETTLEMENT"
    DUPLICATE_PAYMENT = "DUPLICATE_PAYMENT"
    MISSING_IN_RAZORPAY = "MISSING_IN_RAZORPAY"
    MISSING_IN_MERCHANT = "MISSING_IN_MERCHANT"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    FEE_DISCREPANCY = "FEE_DISCREPANCY"
    SETTLEMENT_MISMATCH = "SETTLEMENT_MISMATCH"
    ORPHAN_DEPOSIT = "ORPHAN_DEPOSIT"
    MISSING_RECORD = "MISSING_RECORD"
    REQUIRES_MANUAL_REVIEW = "REQUIRES_MANUAL_REVIEW"


class MatchPhase(str, Enum):
    PHASE_1 = "Phase 1: Direct Key Matching"
    PHASE_2 = "Phase 2: Settlement Batch Matching"
    PHASE_3 = "Phase 3: Fuzzy/Subset-Sum Matching"
    PHASE_4 = "Phase 4: AI Anomaly Investigation"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ─── Data Models ─────────────────────────────────────────────────────────────

class MerchantOrder(BaseModel):
    order_id: str
    customer_name: str
    amount: float
    order_date: datetime
    status: str
    product: str


class RazorpayTransaction(BaseModel):
    payment_id: str
    order_id: str
    amount: float
    fee: float
    tax: float
    net_amount: float
    settlement_id: str
    payment_date: datetime
    settlement_date: date
    status: str


class BankDeposit(BaseModel):
    utr_number: str
    deposit_amount: float
    deposit_date: date
    description: str
    bank_ref: str


class GroundTruth(BaseModel):
    order_id: str
    injected_anomaly_type: str


# ─── Result Models ───────────────────────────────────────────────────────────

class MatchResult(BaseModel):
    """A single matched or flagged transaction."""
    order_id: str
    merchant_amount: Optional[float] = None
    razorpay_amount: Optional[float] = None
    razorpay_net: Optional[float] = None
    bank_deposit: Optional[float] = None
    settlement_id: Optional[str] = None
    utr_number: Optional[str] = None
    status: MatchStatus
    phase: Optional[str] = None
    anomaly_type: Optional[str] = None
    note: Optional[str] = None


class AnomalyDetail(BaseModel):
    """Detailed anomaly with AI investigation results."""
    order_id: str
    anomaly_type: str
    detected_in_phase: str
    merchant_data: Optional[dict] = None
    razorpay_data: Optional[dict] = None
    bank_data: Optional[dict] = None
    ai_explanation: Optional[str] = None
    ai_classification: Optional[str] = None
    ai_confidence: Optional[str] = None
    ai_suggested_resolution: Optional[str] = None
    needs_manual_review: bool = False


class PhaseStats(BaseModel):
    """Stats for a single reconciliation phase."""
    phase_name: str
    input_count: int
    matched_count: int
    anomaly_count: int
    remaining_count: int


class ReconciliationReport(BaseModel):
    """Final reconciliation report with all results."""
    total_merchant_orders: int
    total_razorpay_transactions: int
    total_bank_deposits: int
    total_matched: int
    total_anomalies: int
    match_rate: float
    phase_stats: list[PhaseStats]
    matched_results: list[MatchResult]
    anomalies: list[AnomalyDetail]
    # Scoring
    ai_accuracy: Optional[float] = None
    ai_correct: Optional[int] = None
    ai_total: Optional[int] = None
    engine_accuracy: Optional[float] = None
