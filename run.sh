#!/usr/bin/env bash
# ==============================================================================
# ReconX — One-Click Launcher for macOS & Linux
# Architect: K Yashwanth Kumar | Razorpay Buildathon
# ==============================================================================

set -e

echo "==============================================================================="
echo "               ReconX -- Automated Ledger Reconciliation Engine"
echo "           Track 04: AI Finance Controller - Razorpay Buildathon"
echo "==============================================================================="
echo ""

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed or not in PATH."
    echo "Please install Python 3.10+ (e.g. via brew install python or apt install python3)."
    exit 1
fi

# 2. Virtual environment setup
if [ ! -d "venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv venv
fi

# 3. Activate venv
source venv/bin/activate

# 4. Install dependencies
echo "[SETUP] Checking and installing dependencies..."
pip install -r requirements.txt --quiet --disable-pip-version-check

# 5. Environment config check
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[INFO] Created .env template."
fi

echo ""
echo "==============================================================================="
echo " [SUCCESS] ReconX is starting! Point your browser to http://localhost:8501"
echo "==============================================================================="
echo ""

# 6. Run Streamlit
streamlit run dashboard/app.py
