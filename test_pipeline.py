"""Checks the pipeline against what generate_data.py planted (data/ground_truth.json)."""
import json

from frp.pipeline import run_pipeline

truth = json.load(open("data/ground_truth.json"))
planted, both = truth["planted_in_issues_file"], truth["present_in_both_files"]


def types(result):
    return {a["type"] for a in result["alerts"]}


def flagged(result, type_):
    return {n for a in result["alerts"] if a["type"] == type_ for n in a["invoice_nos"]}


# ---- file with problems: every planted problem must be caught
bad = run_pipeline("data/invoices_with_issues.xlsx", "data/bank_statement.csv")
assert bad["status"] == "needs_fixes"
assert any(a["type"] == "missing_month" and planted["missing_month"] in a["message"] for a in bad["alerts"])
assert flagged(bad, "duplicate_invoice") == set(planted["duplicate_invoice_numbers"])
assert "buyer_name_variants" in types(bad)
assert flagged(bad, "no_bank_match") == set(both["invoices_without_bank_payment"])
assert bad["indicators"]["top_buyer"]["name"] == both["dominant_buyer"]

# ---- clean file: no blocking problems and no false alarms
clean = run_pipeline("data/invoices_clean.xlsx", "data/bank_statement.csv")
assert clean["status"] == "ready"
assert types(clean) == {"no_bank_match"}, types(clean)     # the 6 unpaid invoices are a real risk
assert flagged(clean, "no_bank_match") == set(both["invoices_without_bank_payment"])
assert clean["cleaning_log"] == []                           # nothing needed fixing
assert abs(clean["indicators"]["top_buyer"]["share"] - both["dominant_buyer_revenue_share"]) < 0.01

print("All checks passed.")
for name, r in (("with issues", bad), ("clean", clean)):
    print(f"\n== {name}: status={r['status']}, alerts={len(r['alerts'])}, log entries={len(r['cleaning_log'])}")
    for a in r["alerts"]:
        print(f"  [{a['severity']}] {a['type']}: {a['message'][:140]}")
    print("  recommendation:", {k: v for k, v in r["recommendation"].items() if k != "reasons"})
print("\nindicators (clean):", json.dumps({k: v for k, v in clean["indicators"].items() if k != "revenue_by_month"}, indent=1))
