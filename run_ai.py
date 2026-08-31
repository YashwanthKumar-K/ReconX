from engine.reconciliation_engine import run_reconciliation
from engine.ai_investigator import investigate_batch, save_ai_cache
report = run_reconciliation("data/sample", use_ai=False, verbose=False)
anomalies = report["anomalies"]
print(f"Found {len(anomalies)} anomalies. Running AI...")
investigate_batch(anomalies)
save_ai_cache(anomalies, "data/sample/cached_ai_results.json")
print("Saved cache.")
