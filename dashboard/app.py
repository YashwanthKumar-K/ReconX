"""
ReconX Dashboard — Streamlit App

Single-page interactive dashboard for the reconciliation engine.
"""
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
from pathlib import Path


# ─── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ReconX — Ledger Reconciliation",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .stApp {
        background-color: #0c0f17;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .metric-card {
        background: #141a26;
        border: 1px solid #1f293d;
        border-radius: 8px;
        padding: 18px;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 600;
        color: #f8fafc;
        letter-spacing: -0.5px;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 4px;
    }
    div[data-testid="stMetric"] {
        background: #141a26;
        border: 1px solid #1f293d;
        border-radius: 8px;
        padding: 14px 18px;
    }
    .phase-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    .badge-high { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-medium { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-low { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
    
    .enterprise-header {
        padding: 6px 0 16px 0;
        border-bottom: 1px solid #1e293b;
        margin-bottom: 20px;
    }
    .brand-title {
        font-size: 1.85rem;
        font-weight: 700;
        color: #ffffff;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .brand-subtitle {
        color: #94a3b8;
        font-size: 0.95rem;
        margin: 4px 0 0 0;
    }
    .spec-card {
        background: #111622;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 16px 18px;
        height: 100%;
    }
    .spec-title {
        font-size: 0.92rem;
        font-weight: 600;
        color: #e2e8f0;
        margin-bottom: 6px;
    }
    .spec-desc {
        font-size: 0.83rem;
        color: #94a3b8;
        line-height: 1.45;
        margin: 0;
    }
    .spec-meta {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px solid #1e293b;
    }
</style>
""", unsafe_allow_html=True)


# ─── Header ──────────────────────────────────────────────────────────────────

st.markdown("""
<div class="enterprise-header">
    <div style="display: flex; justify-content: space-between; align-items: baseline;">
        <div>
            <h1 class="brand-title">ReconX</h1>
            <p class="brand-subtitle">Automated Multi-Way Ledger Reconciliation & AI Anomaly Resolution Engine</p>
        </div>
        <div style="text-align: right;">
            <span style="font-size: 0.78rem; color: #94a3b8; background: #141a26; padding: 4px 10px; border-radius: 4px; border: 1px solid #1f293d;">
                Razorpay Buildathon · Track 04
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Sidebar Settings ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Matching Parameters")
    from engine.config import config
    config.expected_fee_rate = st.number_input("Razorpay Fee Rate (%)", value=config.expected_fee_rate * 100, step=0.1) / 100.0
    config.fee_rate_tolerance = st.number_input("Fee Rate Tolerance (%)", value=config.fee_rate_tolerance * 100, step=0.1) / 100.0
    config.amount_tolerance = st.number_input("Amount Tolerance (₹)", value=config.amount_tolerance, step=0.01)
    
    st.markdown("---")
    st.markdown("### AI Inference Stack")
    st.markdown(
        """
        - **Primary:** Groq (Llama 3 70B)
        - **Secondary:** NVIDIA NIM (Llama 3.1 70B)
        - **Tertiary:** Google Gemini 1.5 Flash
        - **Fallback:** Deterministic Classifier
        """
    )
    st.markdown("---")
    st.caption("Engine architecture: Pure deterministic matching for computable arithmetic; LLM agents for contextual exception analysis.")


# ─── Session State ────────────────────────────────────────────────────────────

if "report" not in st.session_state:
    st.session_state.report = None
if "running" not in st.session_state:
    st.session_state.running = False


# ─── Data Loading Section ────────────────────────────────────────────────────

col_load1, col_load2, col_load3 = st.columns([2, 2, 2])

with col_load1:
    sample_btn = st.button(
        "Load Sample Data (50 orders)",
        use_container_width=True,
        type="primary",
    )

with col_load2:
    sample_500_btn = st.button(
        "Generate 500 Orders",
        use_container_width=True,
    )

with col_load3:
    uploaded_files = st.file_uploader(
        "Or upload your own CSVs",
        type=["csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

# Handle data loading
data_dir = None

if sample_btn:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample")
    st.session_state.data_dir = data_dir
    st.session_state.data_size = 50

if sample_500_btn:
    from engine.synthetic_data_generator import generate_data
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "generated_500")
    with st.spinner("Generating 500 orders..."):
        generate_data(num_orders=500, output_dir=out_dir, seed=123)
    data_dir = out_dir
    st.session_state.data_dir = data_dir
    st.session_state.data_size = 500

if uploaded_files and len(uploaded_files) >= 3:
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploaded")
    os.makedirs(upload_dir, exist_ok=True)

    # 1. Clear only known CSV files — avoids WinError 5 from rmtree on locked dirs
    for stale in ["merchant_orders.csv", "razorpay_transactions.csv",
                   "bank_statement.csv", "ground_truth.csv", "cached_ai_results.json"]:
        stale_path = os.path.join(upload_dir, stale)
        try:
            if os.path.exists(stale_path):
                os.remove(stale_path)
        except OSError:
            pass  # File locked — overwrite below will still work

    
    # 2. Save files using strict whitelisted names
    saved_count = 0
    for f in uploaded_files:
        name_lower = f.name.lower()
        target_name = None
        if "ground" in name_lower or "truth" in name_lower or "answer" in name_lower:
            target_name = "ground_truth.csv"  # optional — enables accuracy scoring
        elif "merchant" in name_lower or "order" in name_lower:
            target_name = "merchant_orders.csv"
        elif "razorpay" in name_lower or "transaction" in name_lower:
            target_name = "razorpay_transactions.csv"
        elif "bank" in name_lower or "statement" in name_lower:
            target_name = "bank_statement.csv"

        if target_name:
            with open(os.path.join(upload_dir, target_name), "wb") as out:
                out.write(f.getbuffer())
            if target_name != "ground_truth.csv":
                saved_count += 1  # only count the 3 required ledger files

    if saved_count >= 3:
        data_dir = upload_dir
        st.session_state.data_dir = data_dir
        has_gt = os.path.exists(os.path.join(upload_dir, "ground_truth.csv"))
        msg = "Loaded and normalized 3 ledger files!"
        if has_gt:
            msg += " Ground truth detected — accuracy scoring enabled."
        msg += " Click RECONCILE below."
        st.success(msg)

    else:
        st.error("Could not identify the 3 required files. Please ensure names contain 'merchant', 'razorpay', and 'bank'.")

if data_dir or "data_dir" in st.session_state:
    active_dir = data_dir or st.session_state.get("data_dir")

    # ─── Reconcile Button ────────────────────────────────────────────
    col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
    with col_r1:
        use_ai = st.checkbox("Enable AI Investigation (Phase 4)", value=True,
                             help="Uses Groq (Llama3) or Gemini to explain each anomaly")
    with col_r2:
        cache_path = os.path.join(active_dir, "cached_ai_results.json")
        has_cache = os.path.exists(cache_path)
        use_cache = st.checkbox(
            "Use Cached AI Results (Demo Mode)",
            value=has_cache,
            disabled=not has_cache,
            help="Load pre-computed AI results instantly. Run once with Live AI to build the cache."
        )
    with col_r3:
        reconcile_btn = st.button("RECONCILE", type="primary", use_container_width=True)

    if reconcile_btn:
        st.session_state.running = True
        import time
        start_time = time.time()

        progress_bar = st.progress(0, text="Starting reconciliation...")

        from engine.reconciliation_engine import run_reconciliation
        from engine.csv_parser import CSVValidationError

        # Step 1: Deterministic matching (instant ~0.03s)
        progress_bar.progress(10, text="Phase 1-3: Running deterministic matching...")
        
        try:
            report = run_reconciliation(data_dir=active_dir, use_ai=False, verbose=False)
        except CSVValidationError as e:
            progress_bar.empty()
            st.error(f"🚨 **CSV Validation Error:** {str(e)}\n\nPlease check the required column names in the README and re-upload your files.")
            st.session_state.running = False
            st.stop()
        except Exception as e:
            progress_bar.empty()
            st.error(f"🚨 **Unexpected Error:** {str(e)}")
            st.session_state.running = False
            st.stop()

        progress_bar.progress(50, text="Deterministic matching complete!")

        # Step 2: AI investigation
        if use_ai and report.get("anomalies"):
            from engine.ai_investigator import investigate_batch, load_ai_cache, save_ai_cache
            from engine.scorer import score_results
            from engine.csv_parser import parse_ground_truth
            from pathlib import Path
            import time as _time

            anomalies = report["anomalies"]

            if use_cache and has_cache:
                # Fix 2: Load from cache -- instant, zero API calls
                progress_bar.progress(90, text="Loading cached AI results...")
                enriched = load_ai_cache(anomalies, cache_path)
            else:
                # Live AI call -- batch all anomalies in ONE request (Fix 1)
                def on_progress(current, total, message):
                    pct = 50 + int((current / max(total, 1)) * 40)
                    progress_bar.progress(pct, text=f"AI: {message}")

                enriched = investigate_batch(anomalies, progress_callback=on_progress)
                # Save cache for future demo runs (Fix 2)
                save_ai_cache(enriched, cache_path)
                st.toast("AI results cached for next run!", icon="💾")

            report["anomalies"] = enriched

            # Re-score with AI results
            gt_path = Path(active_dir) / "ground_truth.csv"
            if gt_path.exists():
                gt_df = parse_ground_truth(str(gt_path))
                matched_ids = set(m["order_id"] for m in report.get("matched_results", []))
                scores = score_results(enriched, gt_df, matched_ids)
                report["scores"] = scores

        progress_bar.progress(100, text="Complete!")
        time.sleep(0.3)
        progress_bar.empty()

        # Update total elapsed time to include AI Phase
        total_time = round(time.time() - start_time, 2)
        report["elapsed_seconds"] = total_time

        st.session_state.report = report
        st.session_state.running = False
        st.rerun()


# ─── Results Dashboard ───────────────────────────────────────────────────────

if st.session_state.report is not None:
    report = st.session_state.report

    st.markdown("---")
    st.markdown("## Dashboard")

    # ─── Hero Stats ───────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric("Total Orders", report["total_merchant_orders"])
    with c2:
        st.metric("Matched", report["total_matched"], delta=f"{report['match_rate']}%")
    with c3:
        st.metric("Anomalies", report["total_anomalies"])
    with c4:
        engine_acc = report["scores"]["engine_accuracy"]
        st.metric("Engine Accuracy", f"{engine_acc}%" if engine_acc is not None else "N/A",
                  help="Only available when ground_truth.csv is present")
    with c5:
        ai_acc = report["scores"]["ai_accuracy"]
        ai_label = f"{ai_acc}%" if ai_acc is not None else "N/A"
        ai_delta = f"{report['scores']['ai_correct']}/{report['scores']['ai_total']}" if ai_acc is not None else None
        st.metric("AI Accuracy", ai_label, delta=ai_delta,
                  help="Only available when ground_truth.csv is present")

    st.markdown("---")

    # ─── Phase Funnel & Tabs ──────────────────────────────────────────
    tab_funnel, tab_matched, tab_anomalies, tab_settlements, tab_accuracy, tab_export = st.tabs([
        "Phase Breakdown",
        "Matched Transactions",
        "Anomalies",
        "Settlements",
        "Accuracy & Analytics",
        "Export Reports",
    ])

    with tab_funnel:
        st.markdown("### Reconciliation Funnel — Orders resolved at each phase")

        phase_stats = report["phase_stats"]
        total_orders = report["total_merchant_orders"]

        # Compute order-level counts for each phase
        p1_matched   = phase_stats[0]["matched_count"]   # orders matched directly
        p1_anomalies = phase_stats[0]["anomaly_count"]   # orders flagged in Phase 1
        p2_matched   = phase_stats[1].get("orders_resolved", 0)  # orders resolved via settlements
        p3_matched   = phase_stats[2]["matched_count"]   # orders resolved via subset-sum
        
        # Phase 3 resolves at the SETTLEMENT level, not the order level.
        # The 9 orders in setl_002 were already counted in Phase 1.
        # Adding p3_matched (=1 settlement) to an order count would be a units mismatch.
        # Funnel stays at order-level throughout; settlement resolution shown separately.
        order_resolved   = p1_matched + p2_matched   # strictly order-level matched
        p3_settlements   = phase_stats[2]["matched_count"]  # settlements resolved by Phase 3

        # Use total_anomalies for the exception bar (includes settlement + bank level)
        total_anomalies = report["total_anomalies"]

        funnel_data = pd.DataFrame([
            {"Phase": "Input Orders",                    "Count": total_orders},
            {"Phase": "Phase 1: Direct Match",           "Count": p1_matched},
            {"Phase": "Phase 2: Settlement Match",       "Count": p1_matched + p2_matched},
            {"Phase": "Phase 3: Settlement Resolved",    "Count": p1_matched + p2_matched},  # stays same — settlement level
            {"Phase": "Total Anomalies / Exceptions",    "Count": total_anomalies},
        ])

        fig_funnel = go.Figure(go.Funnel(
            y=funnel_data["Phase"],
            x=funnel_data["Count"],
            textinfo="value+percent initial",
            marker=dict(color=["#667eea", "#4caf50", "#2196f3", "#ff9800", "#ff4b4b"]),
        ))
        fig_funnel.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            height=400,
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_funnel, width='stretch')

        # Summary — math must check out: matched + anomalies = total_orders
        col_m, col_a, col_s = st.columns(3)
        col_m.success(f"**Orders Resolved:** {order_resolved} / {total_orders} ({round(order_resolved/total_orders*100,1)}%)")
        col_a.error(f"**Exceptions Flagged:** {total_anomalies} (order + settlement level)")
        col_s.info(f"**Settlements resolved by Phase 3:** {p3_settlements}")


        # Phase stats table
        st.markdown("#### Phase Details")
        st.markdown("""
| Phase | What it counts | Input | Resolved | Anomalies flagged |
|-------|---------------|-------|----------|-------------------|
| Phase 1: Direct Key Matching | Orders matched by order_id | {} orders | {} orders | {} |
| Phase 2: Settlement Batch Matching | Bank deposits matched to Razorpay settlements | {} settlements | {} settlements | {} |
| Phase 3: Fuzzy/Subset-Sum Matching | Remaining settlements via graph matching | {} | {} | {} |
| Phase 4: AI Investigation | Anomalies explained by AI | {} anomalies | — | {} investigated |
""".format(
            phase_stats[0]["input_count"], phase_stats[0]["matched_count"], phase_stats[0]["anomaly_count"],
            phase_stats[1]["input_count"], phase_stats[1]["matched_count"], phase_stats[1]["anomaly_count"],
            phase_stats[2]["input_count"], phase_stats[2]["matched_count"], phase_stats[2]["anomaly_count"],
            phase_stats[3]["input_count"], phase_stats[3]["anomaly_count"],
        ))


    with tab_matched:
        st.markdown("### Matched Transactions — 3-Way View")

        if report["matched_results"]:
            matched_df = pd.DataFrame(report["matched_results"])
            display_cols = ["order_id", "merchant_amount", "razorpay_amount", "razorpay_net",
                           "settlement_id", "phase"]
            available_cols = [c for c in display_cols if c in matched_df.columns]
            st.dataframe(
                matched_df[available_cols],
                width='stretch',
                height=400,
            )
        else:
            st.info("No matched transactions to display.")

    with tab_anomalies:
        st.markdown("### Anomaly Investigation Panel")

        if report["anomalies"]:
            all_anomalies = report["anomalies"]
            num_anomalies = len(all_anomalies)

            # Summary table (always shown — lightweight)
            summary_rows = [{
                "Order ID": a.get("order_id", ""),
                "Type": a.get("ai_classification", a.get("anomaly_type", "")),
                "Confidence": a.get("ai_confidence", ""),
                "Provider": a.get("ai_provider", ""),
                "Phase": a.get("detected_in_phase", ""),
            } for a in all_anomalies]
            st.dataframe(pd.DataFrame(summary_rows), width='stretch', height=300)

            # Paginated detail view
            PAGE_SIZE = 25
            total_pages = max(1, (num_anomalies + PAGE_SIZE - 1) // PAGE_SIZE)
            page = st.number_input(
                f"Page (1–{total_pages}) — {num_anomalies} anomalies total",
                min_value=1, max_value=total_pages, value=1, step=1
            )
            start_idx = (page - 1) * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, num_anomalies)

            for i in range(start_idx, end_idx):
                anomaly = all_anomalies[i]
                confidence = anomaly.get("ai_confidence", "low")

                with st.expander(
                    f"{'🔴' if confidence == 'high' else '🟡' if confidence == 'medium' else '🟢'} "
                    f"{anomaly.get('order_id', 'Unknown')} — "
                    f"{anomaly.get('ai_classification', anomaly.get('anomaly_type', 'Unknown'))}",
                    expanded=(i == start_idx),
                ):
                    col_l, col_r = st.columns([1, 1])

                    with col_l:
                        st.markdown("**Detection Details**")
                        st.write(f"**Type:** {anomaly.get('anomaly_type', 'N/A')}")
                        st.write(f"**Detected in:** {anomaly.get('detected_in_phase', 'N/A')}")

                        if anomaly.get("merchant_data"):
                            st.markdown("**Merchant Data:**")
                            st.json(anomaly["merchant_data"])
                        if anomaly.get("razorpay_data"):
                            st.markdown("**Razorpay Data:**")
                            if isinstance(anomaly["razorpay_data"], list):
                                for rd in anomaly["razorpay_data"]:
                                    st.json(rd)
                            else:
                                st.json(anomaly["razorpay_data"])
                        if anomaly.get("bank_data"):
                            st.markdown("**Bank Data:**")
                            st.json(anomaly["bank_data"])

                    with col_r:
                        st.markdown("**AI Investigation**")

                        # AI explanation in a styled box
                        explanation = anomaly.get("ai_explanation", "No explanation available.")
                        st.info(explanation)

                        st.write(f"**Provider:** `{anomaly.get('ai_provider', 'Unknown')}`")
                        st.write(f"**Classification:** `{anomaly.get('ai_classification', 'N/A')}`")
                        st.write(f"**Confidence:** `{confidence}`")
                        st.write(f"**Resolution:** {anomaly.get('ai_suggested_resolution', 'N/A')}")
                        st.write(f"**Manual Review:** {'Yes' if anomaly.get('needs_manual_review') else 'No'}")
        else:
            st.success("No anomalies detected! All transactions matched cleanly.")

    with tab_settlements:
        st.markdown("### Settlement Batch Matching")

        if report.get("settlement_matches"):
            all_settlements = report["settlement_matches"]
            num_settlements = len(all_settlements)

            # Summary table (lightweight)
            setl_summary = [{
                "Settlement ID": sm.get("settlement_id", ""),
                "Expected (₹)": f"{sm.get('expected_amount', 0):,.2f}",
                "Bank Deposit (₹)": f"{sm.get('bank_amount', 0):,.2f}",
                "UTR": sm.get("utr_number", ""),
                "Orders": sm.get("order_count", 0),
                "Status": sm.get("status", ""),
            } for sm in all_settlements]
            st.dataframe(pd.DataFrame(setl_summary), width='stretch', height=300)

            # Paginated detail view
            SETL_PAGE = 25
            setl_pages = max(1, (num_settlements + SETL_PAGE - 1) // SETL_PAGE)
            if setl_pages > 1:
                setl_page = st.number_input(
                    f"Page (1–{setl_pages}) — {num_settlements} settlements total",
                    min_value=1, max_value=setl_pages, value=1, step=1, key="setl_page"
                )
            else:
                setl_page = 1
            s_start = (setl_page - 1) * SETL_PAGE
            s_end = min(s_start + SETL_PAGE, num_settlements)

            for sm in all_settlements[s_start:s_end]:
                status_icon = "✅" if sm.get("status") == "matched" else "⚠️"
                with st.expander(
                    f"{status_icon} Settlement {sm.get('settlement_id', 'N/A')} — "
                    f"Rs.{sm.get('expected_amount', 0):,.2f} | "
                    f"{sm.get('order_count', 0)} orders",
                ):
                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        st.write(f"**Expected:** Rs.{sm.get('expected_amount', 0):,.2f}")
                        st.write(f"**Bank Deposit:** Rs.{sm.get('bank_amount', 0):,.2f}")
                        st.write(f"**UTR:** {sm.get('utr_number', 'N/A')}")
                    with col_s2:
                        st.write(f"**Settlement Date:** {sm.get('settlement_date', 'N/A')}")
                        st.write(f"**Deposit Date:** {sm.get('deposit_date', 'N/A')}")
                        if sm.get("note"):
                            st.write(f"**Note:** {sm['note']}")
                    # Truncate order list for readability
                    order_ids = sm.get("order_ids", [])
                    if len(order_ids) > 20:
                        st.write(f"**Orders ({len(order_ids)}):** {', '.join(order_ids[:20])}, ...")
                    else:
                        st.write(f"**Orders:** {', '.join(order_ids)}")
        else:
            st.info("No settlement data available.")

    with tab_accuracy:
        scores = report.get("scores") or {}

        if scores.get("engine_accuracy") is not None:
            st.markdown("### Ground Truth Validation & Benchmarks")
            st.markdown(
                "Evaluates engine detection and AI classification accuracy against labeled ground truth."
            )

            col_acc1, col_acc2 = st.columns(2)
            with col_acc1:
                st.markdown("#### Engine Detection Accuracy")
                fig_eng = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=scores["engine_accuracy"],
                    title={"text": "Engine Accuracy %"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": "#22c55e"},
                        "bgcolor": "#141a26",
                        "steps": [
                            {"range": [0, 60], "color": "rgba(239, 68, 68, 0.2)"},
                            {"range": [60, 85], "color": "rgba(245, 158, 11, 0.2)"},
                            {"range": [85, 100], "color": "rgba(34, 197, 94, 0.2)"},
                        ],
                    },
                ))
                fig_eng.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=240,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_eng, width='stretch')
                ec = scores.get("engine_correct", 0)
                et = scores.get("engine_total", 0)
                st.write(f"Correctly identified: **{ec}/{et}** records")

            with col_acc2:
                st.markdown("#### AI Classification Accuracy")
                fig_ai = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=scores.get("ai_accuracy", 0.0),
                    title={"text": "AI Accuracy %"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": "#3b82f6"},
                        "bgcolor": "#141a26",
                        "steps": [
                            {"range": [0, 60], "color": "rgba(239, 68, 68, 0.2)"},
                            {"range": [60, 85], "color": "rgba(245, 158, 11, 0.2)"},
                            {"range": [85, 100], "color": "rgba(59, 130, 246, 0.2)"},
                        ],
                    },
                ))
                fig_ai.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=240,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_ai, width='stretch')
                st.write(f"Correctly diagnosed: **{scores.get('ai_correct', 0)}/{scores.get('ai_total', 0)}** anomalies")

            if scores.get("ai_details"):
                st.markdown("#### Ground Truth vs AI Predictions")
                try:
                    details_df = pd.DataFrame(scores["ai_details"])
                    st.dataframe(details_df, width='stretch', height=260)
                except Exception as e:
                    st.warning(f"Could not format classification details: {e}")

            if scores.get("undetected_anomalies"):
                st.markdown("#### Undetected Exceptions")
                st.warning(f"{len(scores['undetected_anomalies'])} ground-truth anomalies were not captured by the deterministic rules:")
                try:
                    undetected_df = pd.DataFrame(scores["undetected_anomalies"])
                    st.dataframe(undetected_df, width='stretch', height=180)
                except Exception:
                    pass
            else:
                st.success("All injected ground truth anomalies were successfully detected!")

            if scores.get("confusion_matrix"):
                st.markdown("#### Anomaly Confusion Matrix")
                try:
                    cm = scores["confusion_matrix"]
                    cm_df = pd.DataFrame(cm).fillna(0).astype(int)
                    st.dataframe(cm_df, width='stretch')
                except Exception:
                    st.dataframe(pd.DataFrame(scores.get("confusion_matrix", {})), width='stretch')

        else:
            # Custom uploaded dataset (no ground truth key)
            st.markdown("### Anomaly Telemetry & Diagnostics")
            st.markdown(
                "Operational telemetry for uploaded dataset (Ground truth benchmark key is not attached)."
            )

            anomalies = report.get("anomalies", [])
            if anomalies:
                type_counts = {}
                conf_counts = {"high": 0, "medium": 0, "low": 0}
                manual_count = 0

                for a in anomalies:
                    t = a.get("ai_classification") or a.get("anomaly_type") or "UNKNOWN"
                    type_counts[t] = type_counts.get(t, 0) + 1
                    conf = a.get("ai_confidence", "low").lower()
                    conf_counts[conf] = conf_counts.get(conf, 0) + 1
                    if a.get("needs_manual_review"):
                        manual_count += 1

                c_m1, c_m2, c_m3 = st.columns(3)
                c_m1.metric("Flagged Exceptions", len(anomalies))
                c_m2.metric("High Confidence Diagnoses", conf_counts.get("high", 0))
                c_m3.metric("Manual Review Queue", manual_count)

                st.markdown("#### Anomaly Type Distribution")
                type_df = pd.DataFrame(list(type_counts.items()), columns=["Anomaly Type", "Count"]).sort_values("Count", ascending=False)
                st.dataframe(type_df, width='stretch', height=240)
            else:
                st.success("Clean ledger match: 0 exceptions detected.")

    with tab_export:
        st.markdown("### Export Reconciliation Reports")
        st.markdown("Download audited ledger reconciliation summaries and detailed anomaly investigation sheets:")

        exp_col1, exp_col2 = st.columns(2)

        try:
            with exp_col1:
                anomaly_rows = [{
                    "order_id":             a.get("order_id", ""),
                    "anomaly_type":         a.get("anomaly_type", ""),
                    "ai_classification":    a.get("ai_classification", ""),
                    "confidence":           a.get("ai_confidence", ""),
                    "explanation":          a.get("ai_explanation", ""),
                    "suggested_resolution": a.get("ai_suggested_resolution", ""),
                    "needs_manual_review":  a.get("needs_manual_review", True),
                    "detected_in_phase":    a.get("detected_in_phase", ""),
                } for a in report.get("anomalies", [])]

                import io as _io
                csv_buf = _io.StringIO()
                pd.DataFrame(anomaly_rows).to_csv(csv_buf, index=False)
                st.download_button(
                    label="Download Exception Report (CSV)",
                    data=csv_buf.getvalue(),
                    file_name="reconx_anomaly_report.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="All flagged anomalies with AI explanations and suggested resolutions",
                )

            with exp_col2:
                clean_report = {
                    "total_merchant_orders": report.get("total_merchant_orders", 0),
                    "total_razorpay_transactions": report.get("total_razorpay_transactions", 0),
                    "total_bank_deposits": report.get("total_bank_deposits", 0),
                    "total_matched": report.get("total_matched", 0),
                    "total_anomalies": report.get("total_anomalies", 0),
                    "match_rate": report.get("match_rate", 0),
                    "elapsed_seconds": report.get("elapsed_seconds", 0),
                    "phase_stats": report.get("phase_stats", []),
                    "scores": report.get("scores", {}),
                    "anomalies": report.get("anomalies", []),
                    "settlement_matches": report.get("settlement_matches", []),
                }
                json_data = json.dumps(clean_report, indent=2, default=str)
                st.download_button(
                    label="Download Full Audit Summary (JSON)",
                    data=json_data,
                    file_name="reconx_full_report.json",
                    mime="application/json",
                    use_container_width=True,
                    help="Complete reconciliation report with phase stats, scores, and all anomaly records",
                )

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### Anomaly Data Export Preview")
            if report.get("anomalies"):
                st.dataframe(pd.DataFrame(anomaly_rows), width='stretch', height=300)
        except Exception as e:
            st.error(f"Error generating export files: {e}")

    # ─── Performance Footer ───────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f"*Reconciliation completed in **{report.get('elapsed_seconds', '?')}s** "
        f"| {report['total_merchant_orders']} orders processed "
        f"| Multi-Way Deterministic Validation & AI Diagnostics.*"
    )


# ─── Footer ──────────────────────────────────────────────────────────────────

# ─── Landing Page / Architecture Overview ────────────────────────────────────

if st.session_state.report is None:
    st.markdown("### Ledger Data Sources")
    st.markdown(
        "<p style='color:#94a3b8; font-size:0.9rem; margin-top:-8px;'>ReconX validates and reconciles records across three distinct transaction ledgers:</p>",
        unsafe_allow_html=True
    )

    col_l1, col_l2, col_l3 = st.columns(3)
    with col_l1:
        st.markdown("""
        <div class="spec-card">
            <div class="spec-title">1. Merchant Order Records</div>
            <p class="spec-desc">Order-level transactions exported from the merchant e-commerce platform or ERP backend.</p>
            <div class="spec-meta">Primary Schema: <code>order_id</code>, <code>amount</code>, <code>order_date</code>, <code>status</code></div>
        </div>
        """, unsafe_allow_html=True)
    with col_l2:
        st.markdown("""
        <div class="spec-card">
            <div class="spec-title">2. Razorpay Gateway Ledger</div>
            <p class="spec-desc">Processed payment events, MDR processing fees, 18% GST tax deductions, and batch settlement IDs.</p>
            <div class="spec-meta">Primary Schema: <code>payment_id</code>, <code>fee</code>, <code>tax</code>, <code>net_amount</code>, <code>settlement_id</code></div>
        </div>
        """, unsafe_allow_html=True)
    with col_l3:
        st.markdown("""
        <div class="spec-card">
            <div class="spec-title">3. Bank Statement Deposits</div>
            <p class="spec-desc">Actual bulk settlement credits received in the merchant's nodal bank account.</p>
            <div class="spec-meta">Primary Schema: <code>utr_number</code>, <code>deposit_amount</code>, <code>deposit_date</code>, <code>description</code></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Reconciliation Pipeline Stages")

    p_c1, p_c2, p_c3, p_c4 = st.columns(4)
    with p_c1:
        st.markdown("""
        <div class="spec-card">
            <span class="phase-badge badge-low">STAGE 1</span>
            <div class="spec-title" style="margin-top:8px;">Direct Key Match</div>
            <p class="spec-desc">Deterministic O(1) hash index matching by order_id. Resolves ~90% of volume and validates fee calculation arithmetic.</p>
        </div>
        """, unsafe_allow_html=True)
    with p_c2:
        st.markdown("""
        <div class="spec-card">
            <span class="phase-badge badge-low">STAGE 2</span>
            <div class="spec-title" style="margin-top:8px;">Settlement Match</div>
            <p class="spec-desc">Aggregates gateway batches by settlement_id, sums net amounts, and matches against bank deposits using regex extraction.</p>
        </div>
        """, unsafe_allow_html=True)
    with p_c3:
        st.markdown("""
        <div class="spec-card">
            <span class="phase-badge badge-medium">STAGE 3</span>
            <div class="spec-title" style="margin-top:8px;">Combinatorial Graph</div>
            <p class="spec-desc">Evaluates multi-deposit split settlements with bounded combinatorial pruning to guarantee real-time execution.</p>
        </div>
        """, unsafe_allow_html=True)
    with p_c4:
        st.markdown("""
        <div class="spec-card">
            <span class="phase-badge badge-high">STAGE 4</span>
            <div class="spec-title" style="margin-top:8px;">AI Investigation</div>
            <p class="spec-desc">Remaining edge cases are analyzed across a parallel multi-provider cascade (Groq, NVIDIA NIM, Gemini) for root cause analysis.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("Select a dataset above (or upload custom CSVs) and click **RECONCILE** to initiate the multi-stage pipeline.")


