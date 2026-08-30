"""
ReconX Dashboard — Streamlit App

Single-page interactive dashboard for the reconciliation engine.
"""
import sys
import os

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
    for f in uploaded_files:
        with open(os.path.join(upload_dir, f.name), "wb") as out:
            out.write(f.getbuffer())
    data_dir = upload_dir
    st.session_state.data_dir = data_dir

if data_dir or "data_dir" in st.session_state:
    active_dir = data_dir or st.session_state.get("data_dir")

    # ─── Reconcile Button ────────────────────────────────────────────
    col_r1, col_r2 = st.columns([3, 1])
    with col_r1:
        use_ai = st.checkbox("Enable AI Investigation (Phase 4)", value=True,
                             help="Requires GEMINI_API_KEY in .env file")
    with col_r2:
        reconcile_btn = st.button("⚡ RECONCILE", type="primary", use_container_width=True)

    if reconcile_btn:
        st.session_state.running = True

        # Phase-by-phase progress display
        progress_bar = st.progress(0, text="Starting reconciliation...")

        from engine.reconciliation_engine import run_reconciliation

        # Run the pipeline
        progress_bar.progress(10, text="Loading data...")
        time.sleep(0.3)
        progress_bar.progress(25, text="Phase 1: Direct Key Matching...")
        time.sleep(0.2)

        report = run_reconciliation(
            data_dir=active_dir,
            use_ai=use_ai,
            verbose=False,
        )

        progress_bar.progress(60, text="Phase 2: Settlement Batch Matching...")
        time.sleep(0.2)
        progress_bar.progress(75, text="Phase 3: Subset-Sum Matching...")
        time.sleep(0.2)
        progress_bar.progress(90, text="Phase 4: AI Investigation...")
        time.sleep(0.2)
        progress_bar.progress(100, text="Complete!")
        time.sleep(0.3)
        progress_bar.empty()

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
        st.metric("Engine Accuracy", f"{engine_acc}%")
    with c5:
        ai_acc = report["scores"]["ai_accuracy"]
        st.metric("AI Accuracy", f"{ai_acc}%",
                   delta=f"{report['scores']['ai_correct']}/{report['scores']['ai_total']}")

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
        st.markdown("### Reconciliation Funnel — How Many Matched at Each Phase")

        phase_stats = report["phase_stats"]

        # Funnel chart
        funnel_data = pd.DataFrame([
            {"Phase": "Input Orders", "Count": report["total_merchant_orders"]},
            {"Phase": "Phase 1: Matched", "Count": phase_stats[0]["matched_count"]},
            {"Phase": "Phase 2: Settlements Matched", "Count": phase_stats[1]["matched_count"]},
            {"Phase": "Phase 3: Subset Matches", "Count": phase_stats[2]["matched_count"]},
            {"Phase": "Phase 4: AI Anomalies", "Count": phase_stats[3]["anomaly_count"]},
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

        # Phase stats table
        st.markdown("#### Phase Details")
        for ps in phase_stats:
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.write(f"**{ps['phase_name']}**")
            col_b.write(f"Input: {ps['input_count']}")
            col_c.write(f"Matched: {ps['matched_count']}")
            col_d.write(f"Anomalies: {ps['anomaly_count']}")

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
        st.markdown(
            "This proves our engine and AI are actually correct, not just plausible. "
            "Results are scored against a labeled ground truth dataset."
        )

        scores = report["scores"]

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
            st.write(f"Correctly classified: **{scores['engine_correct']}/{scores['engine_total']}** records")

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
