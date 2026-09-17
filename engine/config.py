import os
from pydantic import BaseModel, Field

class ReconXConfig(BaseModel):
    """Global configuration for the reconciliation engine."""
    expected_fee_rate: float = Field(default=0.02, description="Expected Razorpay fee rate (e.g., 0.02 for 2%)")
    fee_rate_tolerance: float = Field(default=0.003, description="Tolerance for floating point fee discrepancies")
    amount_tolerance: float = Field(default=0.01, description="Tolerance for amount mismatch in INR")
    
    @classmethod
    def load(cls) -> "ReconXConfig":
        return cls(
            expected_fee_rate=float(os.getenv("RECONX_FEE_RATE", "0.02")),
            fee_rate_tolerance=float(os.getenv("RECONX_FEE_TOLERANCE", "0.003")),
            amount_tolerance=float(os.getenv("RECONX_AMOUNT_TOLERANCE", "0.01")),
        )

    def validate_api_keys(self) -> dict[str, bool]:
        """Check presence of LLM API keys for anomaly investigation."""
        return {
            "GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
            "NVIDIA_API_KEY": bool(os.getenv("NVIDIA_API_KEY")),
            "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
        }

# Global singleton config
config: ReconXConfig = ReconXConfig.load()
