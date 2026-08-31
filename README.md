<div align="center">
  <h1>ReconX</h1>
  <p><b>Multi-Way Ledger Reconciliation Engine</b></p>
  <p><i>Built for the Razorpay AI Buildathon — Track 04: AI Finance Controller</i></p>
</div>

> **Algorithms for the math (95%). AI for the reasoning (5%). Both with mathematically proven accuracy.**

ReconX is an enterprise-grade reconciliation engine that automatically matches transactions across three complex financial ledgers: **Merchant Records**, **Razorpay Payments**, and **Bank Deposits**.

When numbers don't match, ReconX doesn't just fail—it deploys a parallel swarm of AI models (Groq, NVIDIA NIM, and Google Gemini) to investigate the discrepancy, explain exactly what went wrong, and suggest a resolution.

---

## 🛑 The Problem: The 100-Hour Finance Nightmare

Every mid-to-large merchant using Razorpay has three completely disjointed sources of truth:

| Ledger | Level of Detail | Example |
|--------|-----------------|---------|
| **Merchant DB** | Order level | "Sold a shirt for ₹1,000" (Order: `ORD_123`) |
| **Razorpay** | Transaction level | "Processed ₹1,000, took ₹20 fee" (Pay: `pay_xyz`) |
| **Bank Account** | Batch level | "Deposited ₹45,230" (Batch: `setl_abc`) |

**The Disconnect:** Razorpay bundles payments into settlements. One bank deposit might cover 50+ orders. If an order was partially refunded, if the settlement was split across two days, or if a fee rate was altered, the totals won't match. Finance teams currently spend hundreds of hours every month in Excel playing detective to figure out *why* a ₹45,230 bank deposit doesn't match a ₹46,000 merchant ledger.

---

## 🚀 The Solution: A Hybrid Pipeline

LLMs are terrible at arithmetic but incredible at semantic reasoning. ReconX enforces a strict architectural boundary: **AI never does math.**

ReconX processes 10,000+ orders in fractions of a second using a **4-Phase Hybrid Pipeline**:

```text
Phase 1: Direct Key Matching (Deterministic HashMaps, ~90% matched)
    ↓ unmatched items
Phase 2: Settlement Batch Matching (Grouping & Summation)
    ↓ unmatched items
Phase 3: Bounded Subset-Sum Matching (Combinatorial Graph matching)
    ↓ true anomalies (~5%)
Phase 4: AI Anomaly Investigation (Parallel LLM reasoning)
```

---

## ✨ The "Hidden Gold" (Engineering Highlights)

We built ReconX to survive enterprise-scale loads and demo-day disasters. Here is what is happening under the hood:

### 1. Parallel Scatter-Gather AI Routing (Zero Token Limits)
If a batch contains 800 anomalies, sending them in a single prompt will crash any LLM due to context limits. ReconX automatically slices anomalies into chunks of 20, spins up a **ThreadPool**, and processes them in parallel. 
* *Result: 10,000 orders with 700 anomalies processed in seconds.*

### 2. The AI Waterfall Fallback
To ensure 100% uptime, ReconX routes traffic through a prioritized, fault-tolerant cascade:
1. **Groq (Llama 3 70B)** — Ultra-fast inference, strict JSON adherence.
2. **NVIDIA NIM (Llama 3.1 70B)** — Steps in automatically if Groq hits a rate limit.
3. **Google Gemini (3.5 Flash)** — The final cloud fallback.
4. **Deterministic Rule-Based Engine** — If all APIs fail (or wifi drops), the engine falls back to hardcoded algorithmic classifications. **ReconX never crashes.**

### 3. Ground Truth Accuracy Scoring
We don't just output AI guesses and hope they look right. ReconX includes a built-in synthetic data generator that injects known, labeled anomalies (e.g., `TIMING_MISMATCH`). The engine automatically grades its own performance, generating an **Accuracy Report and Confusion Matrix**. 

### 4. Bounded Subset-Sum Matching (Anti-NP-Hard)
Finding which transactions sum up to a specific bank deposit is a variation of the Subset-Sum problem (which is NP-Hard). ReconX intelligently prunes the search space using a ±2 day sliding window and max-depth boundaries to guarantee it never hangs on edge cases.

---

## 📊 Dashboard Preview

ReconX ships with a beautiful, responsive Streamlit dashboard featuring:
- **3-Way Matched Transactions View**
- **AI Anomaly Investigation Panel** (with provider badges showing exactly which AI solved the case)
- **Settlement Breakdown**
- **Accuracy & Confusion Matrix Scoring**
- **1-Click CSV/JSON Export**

---

## 💻 Quick Start & Setup

### 1. Installation
```bash
git clone https://github.com/YashwanthKumar-K/ReconX.git
cd ReconX
pip install -r requirements.txt
```

### 2. API Keys
ReconX uses free-tier APIs. Create a `.env` file in the root directory:
```env
# You can comma-separate multiple keys to load-balance!
GROQ_API_KEY="gsk_your_key_here"
NVIDIA_API_KEY="nvapi-your_key_here"
GEMINI_API_KEY="AIza_your_key_here"
```

### 3. Run the App
```bash
# Generate a test dataset of 1000 orders with injected anomalies
python -m engine.synthetic_data_generator 1000 data/sample

# Launch the Dashboard
streamlit run dashboard/app.py
```

---

## 📁 Uploading Your Own Data

You can upload your own datasets via the Streamlit UI. Your CSV files **must exactly match** these schemas:

### 1. `merchant_orders.csv`
- `order_id` *(String)* — Unique identifier
- `amount` *(Number)* — e.g. 1500.50
- `order_date` *(Date/Time)*
- `status` *(String)* — e.g. 'paid'

### 2. `razorpay_transactions.csv`
- `order_id` *(String)* — Matches merchant order
- `payment_id` *(String)* — Unique payment ID
- `settlement_id` *(String)* — Batch ID, e.g., `setl_XYZ`
- `amount` *(Number)* — Gross amount
- `fee` *(Number)* — Standard 2% fee
- `tax` *(Number)* — 18% GST on the fee
- `net_amount` *(Number)* — Amount minus fee and tax
- `payment_date` *(Date/Time)*
- `settlement_date` *(Date)*
- `status` *(String)*

### 3. `bank_statement.csv`
- `utr_number` *(String)* — Bank reference
- `deposit_amount` *(Number)* — Matches Razorpay settlement batch
- `deposit_date` *(Date)*
- `description` *(String)* — Text containing the `settlement_id`

### 4. `ground_truth.csv` (Optional, for accuracy scoring)
- `order_id` *(String)*
- `injected_anomaly_type` *(String)* — Must be one of: `NONE`, `MISSING_RECORD`, `AMOUNT_DISCREPANCY`, `FEE_DISCREPANCY`, `DUPLICATE_PAYMENT`, `PARTIAL_REFUND`, `SPLIT_SETTLEMENT`, `TIMING_MISMATCH`

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Core Engine** | Python, Pandas |
| **Combinatorics** | `itertools`, `concurrent.futures` |
| **AI Orchestration** | Groq (Llama 3), NVIDIA NIM (Llama 3.1), Gemini 1.5 Flash |
| **Frontend** | Streamlit |
| **Data Viz** | Plotly |

---

<div align="center">
  <p><i>"Reconciliation shouldn't be a forensic investigation."</i></p>
</div>
