import os
from pydantic import BaseModel, Field

class ReconXConfig(BaseModel):
    """Global configuration for the reconciliation engine."""
    expected_fee_rate: float = Field(default=0.02, description="Expected Razorpay fee rate (e.g., 0.02 for 2%)")
    fee_rate_tolerance: float = Field(default=0.003, description="Tolerance for floating point fee discrepancies")
    amount_tolerance: float = Field(default=0.01, description="Tolerance for amount mismatch in INR")
    
    @classmethod
    def load(cls):
        return cls(
            expected_fee_rate=float(os.getenv("RECONX_FEE_RATE", "0.02")),
            fee_rate_tolerance=float(os.getenv("RECONX_FEE_TOLERANCE", "0.003")),
            amount_tolerance=float(os.getenv("RECONX_AMOUNT_TOLERANCE", "0.01")),
        )

# Global singleton config
config = ReconXConfig.load()
