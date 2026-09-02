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
        background-color: #0f1117;
    }
    .metric-card {
        background: linear-gradient(135deg, #1a1f2e 0%, #252b3b 100%);
        border: 1px solid #2d3548;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #ffffff;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #8899aa;
        margin-top: 4px;
    }
    .anomaly-card {
        background: #1a1f2e;
        border: 1px solid #2d3548;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .phase-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-high { background: #ff4b4b33; color: #ff4b4b; border: 1px solid #ff4b4b55; }
    .badge-medium { background: #ffa50033; color: #ffa500; border: 1px solid #ffa50055; }
    .badge-low { background: #4caf5033; color: #4caf50; border: 1px solid #4caf5055; }
    .matched-row { background: #1b3a2a; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1f2e 0%, #252b3b 100%);
        border: 1px solid #2d3548;
        border-radius: 12px;
        padding: 16px;
    }
    .title-gradient {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem;
        font-weight: 800;
    }
</style>
""", unsafe_allow_html=True)


# ─── Header ──────────────────────────────────────────────────────────────────

st.markdown('<h1 class="title-gradient">ReconX</h1>', unsafe_allow_html=True)
st.markdown("**Multi-Way Ledger Reconciliation Engine** — Algorithms for 95%, AI for the rest.")
st.markdown("---")

# ─── Sidebar Settings ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    st.markdown("Tweak matching parameters below:")
    from engine.config import config
    config.expected_fee_rate = st.number_input("Razorpay Fee Rate (%)", value=config.expected_fee_rate * 100, step=0.1) / 100.0
    config.fee_rate_tolerance = st.number_input("Fee Tolerance (%)", value=config.fee_rate_tolerance * 100, step=0.1) / 100.0
    config.amount_tolerance = st.number_input("Amount Tolerance (₹)", value=config.amount_tolerance, step=0.01)
    st.markdown("---")
    st.markdown("*These parameters adjust the strictness of Phase 1 (Deterministic Matcher).*")


# ─── Session State ────────────────────────────────────────────────────────────

if "report" not in st.session_state:
    st.session_state.report = None
if "running" not in st.session_state:
    st.session_state.running = False


# ─── Data Loading Section ────────────────────────────────────────────────────

col_load1, col_load2, col_load3 = st.columns([2, 2, 2])

with col_load1:
    sample_btn = st.button(
        "📂 Load Sample Data (50 orders)",
        use_container_width=True,
        type="primary",
    )

with col_load2:
    sample_500_btn = st.button(
        "📊 Generate 500 Orders",
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

    # ─── Phase Funnel ─────────────────────────────────────────────────
    tab_funnel, tab_matched, tab_anomalies, tab_settlements, tab_accuracy = st.tabs([
        "📊 Phase Breakdown",
        "✅ Matched Transactions",
        "⚠️ Anomalies",
        "🏦 Settlements",
        "🎯 Accuracy Report",
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
        st.plotly_chart(fig_funnel, use_container_width=True)

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
                use_container_width=True,
                height=400,
            )
        else:
            st.info("No matched transactions to display.")

    with tab_anomalies:
        st.markdown("### Anomaly Investigation Panel")

        if report["anomalies"]:
            for i, anomaly in enumerate(report["anomalies"]):
                confidence = anomaly.get("ai_confidence", "low")
                badge_class = f"badge-{confidence}"

                with st.expander(
                    f"{'🔴' if confidence == 'high' else '🟡' if confidence == 'medium' else '🟢'} "
                    f"{anomaly.get('order_id', 'Unknown')} — "
                    f"{anomaly.get('ai_classification', anomaly.get('anomaly_type', 'Unknown'))}",
                    expanded=(i == 0),
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
            for sm in report["settlement_matches"]:
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
                    st.write(f"**Orders:** {', '.join(sm.get('order_ids', []))}")
        else:
            st.info("No settlement data available.")

    with tab_accuracy:
        st.markdown("### Accuracy Report — Ground Truth Validation")

        scores = report["scores"]

        if scores.get("engine_accuracy") is None:
            st.info(
                "**Ground truth not available for uploaded data.**\n\n"
                "Accuracy scoring requires a `ground_truth.csv` answer key. "
                "This tab shows live results when using the **Load Sample Data** or "
                "**Generate 500 Orders** buttons which include a labeled ground truth dataset."
            )
        else:
            st.markdown(
                "This proves our engine and AI are actually correct, not just plausible. "
                "Results are scored against a labeled ground truth dataset."
            )

            # Accuracy metrics
            col_acc1, col_acc2 = st.columns(2)
            with col_acc1:
                st.markdown("#### Engine Detection Accuracy")
                fig_eng = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=scores["engine_accuracy"],
                    title={"text": "Engine Accuracy %"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": "#4caf50"},
                        "bgcolor": "#1a1f2e",
                        "steps": [
                            {"range": [0, 60], "color": "#ff4b4b33"},
                            {"range": [60, 85], "color": "#ffa50033"},
                            {"range": [85, 100], "color": "#4caf5033"},
                        ],
                    },
                ))
                fig_eng.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=250,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_eng, use_container_width=True)
                ec = scores.get("engine_correct", "?")
                et = scores.get("engine_total", "?")
                st.write(f"Correctly classified: **{ec}/{et}** records")

            with col_acc2:
                st.markdown("#### AI Classification Accuracy")
                fig_ai = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=scores["ai_accuracy"],
                    title={"text": "AI Accuracy %"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": "#667eea"},
                        "bgcolor": "#1a1f2e",
                        "steps": [
                            {"range": [0, 60], "color": "#ff4b4b33"},
                            {"range": [60, 85], "color": "#ffa50033"},
                            {"range": [85, 100], "color": "#4caf5033"},
                        ],
                    },
                ))
                fig_ai.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=250,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_ai, use_container_width=True)
                st.write(f"Correctly classified: **{scores['ai_correct']}/{scores['ai_total']}** anomalies")

            # AI classification details
            if scores.get("ai_details"):
                st.markdown("#### Classification Details")
                details_df = pd.DataFrame(scores["ai_details"])
                st.dataframe(details_df, use_container_width=True)

            # Undetected anomalies
            if scores.get("undetected_anomalies"):
                st.markdown("#### Undetected Anomalies (Honest Exception List)")
                st.warning(f"{len(scores['undetected_anomalies'])} anomalies were not detected by the engine:")
                for u in scores["undetected_anomalies"]:
                    st.write(f"- **{u['order_id']}**: {u['missed_anomaly_type']}")
            else:
                st.success("All injected anomalies were detected!")

            # Confusion matrix
            if scores.get("confusion_matrix"):
                st.markdown("#### Confusion Matrix")
                cm = scores["confusion_matrix"]
                cm_df = pd.DataFrame(cm).fillna(0).astype(int)
                st.dataframe(cm_df, use_container_width=True)


    # ─── Performance ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f"*Reconciliation completed in **{report.get('elapsed_seconds', '?')}s** "
        f"| {report['total_merchant_orders']} orders processed "
        f"| Algorithms do the math, AI explains the why.*"
    )

    # ─── Export ──────────────────────────────────────────────────────
    if "report" in st.session_state and st.session_state.report:
        st.markdown("### Export Results")
        exp_col1, exp_col2 = st.columns(2)

        # CSV anomaly report
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
            } for a in report["anomalies"]]

            import io as _io
            csv_buf = _io.StringIO()
            pd.DataFrame(anomaly_rows).to_csv(csv_buf, index=False)
            st.download_button(
                label="📥 Download Anomaly Report (CSV)",
                data=csv_buf.getvalue(),
                file_name="reconx_anomaly_report.csv",
                mime="text/csv",
                use_container_width=True,
                help="All flagged anomalies with AI explanations and suggested resolutions",
            )

        # JSON full report
        with exp_col2:
            st.download_button(
                label="📥 Download Full Report (JSON)",
                data=json.dumps(report, indent=2, default=str),
                file_name="reconx_full_report.json",
                mime="application/json",
                use_container_width=True,
                help="Complete reconciliation report with all phase stats, matched results, and scores",
            )


# ─── Footer ──────────────────────────────────────────────────────────────────

if st.session_state.report is None:
    st.markdown("---")
    st.markdown(
        "### How it works\n\n"
        "1. **Phase 1** — Direct key matching: HashMap lookup by `order_id` (~85-90% matched)\n"
        "2. **Phase 2** — Settlement batch matching: Group & sum Razorpay txns, match to bank deposits\n"
        "3. **Phase 3** — Bounded subset-sum: Find combinations of settlements that match deposits\n"
        "4. **Phase 4** — AI investigation: Gemini analyzes remaining anomalies and explains why\n\n"
        "**The key insight:** Algorithms handle what's computable. AI handles what's ambiguous."
    )
