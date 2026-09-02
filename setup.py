from setuptools import setup, find_packages

setup(
    name="reconx",
    version="1.0.0",
    description="Automated Multi-Way Ledger Reconciliation & AI Anomaly Resolution Engine",
    author="K Yashwanth Kumar",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pandas>=2.0.0",
        "networkx>=3.0",
        "streamlit>=1.30.0",
        "plotly>=5.18.0",
        "google-genai>=1.0.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "reconx=engine.reconciliation_engine:main",
        ],
    },
)
