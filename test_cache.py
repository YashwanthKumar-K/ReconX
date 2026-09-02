from engine.reconciliation_engine import run_reconciliation
from engine.ai_investigator import save_ai_cache

report = run_reconciliation('data/generated_8000', use_ai=False, verbose=False)
save_ai_cache(report['anomalies'], 'data/generated_8000/cached_ai_results.json')
print('Cache built for 8000 orders!')
s = report.get('scores', {})
print(f"AI Accuracy: {s.get('ai_accuracy')}% ({s.get('ai_correct')}/{s.get('ai_total')})")
print(f"Engine Accuracy: {s.get('engine_accuracy')}% ({s.get('engine_correct')}/{s.get('engine_total')})")
