@echo off
title ReconX - Multi-Way Ledger Reconciliation Engine
color 0B

echo ===============================================================================
echo                ReconX -- Automated Ledger Reconciliation Engine
echo            Track 04: AI Finance Controller - Razorpay Buildathon
echo ===============================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3.10+ is required but not found on your system PATH.
    echo Please install Python from https://www.python.org/downloads/ and check
    echo "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: 2. Check or create virtual environment
if not exist "venv\" (
    echo [SETUP] Creating isolated Python virtual environment (venv)...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 3. Activate virtual environment
call venv\Scripts\activate.bat

:: 4. Install / Update dependencies
echo [SETUP] Checking and installing dependencies from requirements.txt...
pip install -r requirements.txt --quiet --disable-pip-version-check
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: 5. Create default .env if missing
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [INFO] Created default .env file from template.
    )
)

echo.
echo ===============================================================================
echo  [SUCCESS] ReconX is starting! Your browser will open automatically.
echo  Local Dashboard URL: http://localhost:8501
echo ===============================================================================
echo.

:: 6. Launch Streamlit app
streamlit run dashboard/app.py
pause
