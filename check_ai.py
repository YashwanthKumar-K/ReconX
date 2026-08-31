import pandas as pd, json
gt = pd.read_csv("data/sample/ground_truth.csv")
with open("data/sample/cached_ai_results.json") as f:
    results = json.load(f)
gt_map = dict(zip(gt["order_id"], gt["injected_anomaly_type"]))
wrong = 0
for r in results:
    if "ai_classification" in r:
        ai = r["ai_classification"]
        actual = gt_map.get(r["order_id"], "NONE")
        if ai != actual:
            wrong += 1
            print(f"Order {r['order_id']}: AI said {ai}, Truth was {actual}")
print("Total wrong:", wrong)
