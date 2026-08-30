# ReconX — Multi-Way Ledger Reconciliation Engine

> **Algorithms for 95%. AI for the rest. Both with measured accuracy.**

A smart reconciliation tool that matches transactions across three financial ledgers — Merchant records, Razorpay payments, and Bank deposits — using a 4-phase pipeline that combines deterministic algorithms with AI-powered anomaly investigation.

Built for [Razorpay AI Buildathon](https://razorpay.com/buildathon/) — **Track 04: AI Finance Controller**

---

## The Problem

Every merchant using Razorpay has three sources of truth:

| Source | Records | Example |
|--------|---------|---------|
| **Merchant's DB** | Orders placed | "Sold a shirt for Rs.1,000" |
| **Razorpay** | Payments processed | "Processed Rs.1,000, took Rs.20 fee" |
| **Bank** | Deposits received | "Deposited Rs.45,230" (bundled!) |

**The nightmare:** Razorpay bundles settlements — one bank deposit covers 50+ orders. Finance teams spend **100+ hours/month** in Excel figuring out which orders make up each deposit. When numbers don't match (refunds, timing, errors), it's detective work.

## The Solution

ReconX automates this in seconds with a 4-phase pipeline:

```
Phase 1: Direct Key Matching (HashMap, ~90% matched)
    ↓ remaining
Phase 2: Settlement Batch Matching (Grouping + Sum)
    ↓ remaining
Phase 3: Bounded Subset-Sum Matching (Combinatorial, bounded)
    ↓ remaining (~5%)
Phase 4: AI Anomaly Investigation (Google Gemini)
```

**Key design principle:** LLMs don't do math. Algorithms handle deterministic matching. AI only investigates genuinely ambiguous discrepancies.

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │    Streamlit Dashboard        │
                    │  Upload → Reconcile → View    │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │    Reconciliation Engine       │
                    │                               │
                    │  Phase 1: Direct Key Match    │
                    │  Phase 2: Settlement Match    │
                    │  Phase 3: Subset-Sum Match    │
                    │  Phase 4: AI Investigation    │
                    │  Scorer: Ground Truth Check   │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   Google Gemini (Free Tier)    │
                    │   Structured anomaly analysis │
                    └──────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/ReconX.git
cd ReconX

# Install dependencies
pip install -r requirements.txt

# Set up Gemini API key (free: https://aistudio.google.com/apikey)
cp .env.example .env
# Edit .env and add your key

# Generate sample data
python -m engine.synthetic_data_generator 50 data/sample

# Run the engine (CLI)
python -m engine.reconciliation_engine data/sample

# Launch the dashboard
streamlit run dashboard/app.py
```

## How Each Phase Works

### Phase 1: Direct Key Matching
- Indexes Razorpay transactions by `order_id` in a HashMap
- Matches merchant orders by key lookup
- Detects: amount mismatches, duplicate payments, missing records
- **Fee discrepancy detection is deterministic** — checks if `fee / amount` falls within expected rate ± tolerance. No AI needed for decidable math.

### Phase 2: Settlement Batch Matching
- Groups Razorpay transactions by `settlement_id`
- Sums `net_amount` per settlement batch
- Matches totals against bank deposits (±Rs.1, ±1 day tolerance)
- Detects: settlement mismatches, orphan bank deposits

### Phase 3: Bounded Subset-Sum Matching
- For unmatched items, tries combinations of Razorpay settlements that sum to bank deposits
- **Bounded to avoid NP-hard blowup**: max 4 items per combination, ±2 day date window
- Uses itertools combinations with pruning — demo-safe, no hangs

### Phase 4: AI Anomaly Investigation
- Remaining anomalies (~5%) sent to Google Gemini with full context
- Structured JSON output: root cause, confidence, explanation, resolution
- Scored against ground truth for measured accuracy

## Ground Truth Scoring

Every run produces accuracy metrics:
- **Engine Detection Accuracy**: Did the algorithm correctly identify anomalous vs. clean records?
- **AI Classification Accuracy**: Did the AI correctly classify the anomaly type?
- **Confusion Matrix**: Predicted vs. actual anomaly types
- **Honest Exception List**: Anomalies the engine missed

This proves the system works — not just "looks right."

## Anomaly Types Detected

| Type | Detection | Method |
|------|-----------|--------|
| Fee Discrepancy | Deterministic | Phase 1 rule check |
| Missing in Razorpay | Deterministic | Phase 1 key lookup |
| Duplicate Payment | Deterministic | Phase 1 count check |
| Partial Refund | AI | Phase 4 investigation |
| Timing Mismatch | AI | Phase 4 investigation |
| Split Settlement | AI | Phase 4 investigation |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Engine | Python, Pandas |
| Graph Matching | NetworkX (available), itertools |
| AI | Google Gemini 2.0 Flash (free tier) |
| Dashboard | Streamlit |
| Charts | Plotly |
| Validation | Pydantic |

## Project Structure

```
ReconX/
├── engine/
│   ├── synthetic_data_generator.py   # Generates test data + ground truth
│   ├── csv_parser.py                 # Normalizes CSVs
│   ├── direct_matcher.py             # Phase 1
│   ├── settlement_matcher.py         # Phase 2
│   ├── graph_matcher.py              # Phase 3
│   ├── ai_investigator.py            # Phase 4 (Gemini)
│   ├── reconciliation_engine.py      # Orchestrator
│   ├── scorer.py                     # Ground truth validation
│   └── models.py                     # Data models
├── dashboard/
│   └── app.py                        # Streamlit dashboard
├── data/sample/                      # Pre-generated demo data
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT

---

*Built for the Razorpay AI Buildathon — Track 04: AI Finance Controller*
