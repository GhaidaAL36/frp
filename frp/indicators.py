"""Indicators for the bank analyst, plus a transparent rule-based initial recommendation.
All numbers are computed here in code; nothing is estimated by a model."""
import pandas as pd

# Thresholds are assumptions (documented in the README); a bank would set its own.
TOP_BUYER_LIMIT = 0.35        # share of revenue from one buyer
OVERDUE_RATE_LIMIT = 0.05     # unpaid share of invoices already due
REVENUE_CV_LIMIT = 0.30       # month-to-month variation (std / mean)
MIN_CASH_MONTHS = 0.10        # lowest balance as a share of average monthly revenue
LIMIT_MONTHS_OF_SALES = 1.0   # base limit = 1 month of average sales
HIGH, MEDIUM = 80, 50


def compute_indicators(m, bank, expected_months, as_of):
    as_of = pd.Timestamp(as_of)
    rev = (m.groupby(m["issue_date"].dt.to_period("M"))["subtotal"].sum()
             .reindex(expected_months, fill_value=0.0))
    mean = float(rev.mean())
    by_buyer = (m.groupby("buyer")["subtotal"].sum() / m["subtotal"].sum()).sort_values(ascending=False)

    due = m[m["due_date"] < as_of]
    unpaid = due[~due["paid"]]
    days_over = (as_of - unpaid["due_date"]).dt.days
    buckets = {"1-30": (1, 30), "31-60": (31, 60), "61-90": (61, 90), "90+": (91, 10_000)}
    aging = {k: round(float(unpaid.loc[days_over.between(lo, hi), "total"].sum()), 2)
             for k, (lo, hi) in buckets.items()}

    return {
        "invoice_count": int(len(m)),
        "revenue_by_month": [{"month": str(p), "revenue": round(float(v), 2)} for p, v in rev.items()],
        "avg_monthly_revenue": round(mean, 2),
        "avg_monthly_revenue_last6": round(float(rev.iloc[-6:].mean()), 2),
        "revenue_cv": round(float(rev.std(ddof=0) / mean), 3) if mean else None,
        "weakest_month": str(rev.idxmin()),
        "avg_invoice_value": round(float(m["subtotal"].mean()), 2),
        "top_buyer": {"name": by_buyer.index[0], "share": round(float(by_buyer.iloc[0]), 3)},
        "top3_share": round(float(by_buyer.iloc[:3].sum()), 3),
        "overdue_rate": round(float(unpaid["total"].sum() / due["total"].sum()), 3),
        "overdue_aging_sar": aging,
        "avg_days_late_when_paid": round(float(m.loc[m["paid"], "days_late"].mean()), 1),
        "unmatched_old_invoices": int(((~m["paid"]) & (m["issue_date"] <= as_of - pd.Timedelta(days=75))).sum()),
        "min_bank_balance": round(float(bank["balance"].min()), 2),
        "ending_bank_balance": round(float(bank["balance"].iloc[-1]), 2),
    }


def recommend(ind, alerts):
    """Initial recommendation: suggested limit, confidence, and reasons tied to indicators."""
    reasons, score, factor = [], 100, 1.0

    def reason(effect, text):
        reasons.append({"effect": effect, "text": text})

    if ind["top_buyer"]["share"] > TOP_BUYER_LIMIT:
        score -= 20; factor *= 0.85
        reason("lowers", f"One buyer ({ind['top_buyer']['name']}) is {ind['top_buyer']['share']:.0%} of revenue.")
    else:
        reason("supports", "Revenue is spread across buyers.")
    if ind["overdue_rate"] > OVERDUE_RATE_LIMIT:
        score -= 15; factor *= 0.90
        reason("lowers", f"{ind['overdue_rate']:.1%} of invoices already due are unpaid.")
    else:
        reason("supports", "Collection is healthy: few invoices are overdue.")
    if ind["revenue_cv"] and ind["revenue_cv"] > REVENUE_CV_LIMIT:
        score -= 10
        reason("lowers", f"Monthly revenue varies a lot (variation {ind['revenue_cv']:.0%}).")
    else:
        reason("supports", "Monthly revenue is reasonably stable (seasonal peaks included).")
    if ind["min_bank_balance"] < MIN_CASH_MONTHS * ind["avg_monthly_revenue"]:
        score -= 10; factor *= 0.90
        reason("lowers", f"Bank balance dropped as low as SAR {ind['min_bank_balance']:,.0f}.")

    warnings = [a for a in alerts if a["severity"] == "warning"]
    blocking = [a for a in alerts if a["severity"] == "blocking"]
    if warnings:
        score -= min(15, 5 * len(warnings))
        reason("lowers", f"{len(warnings)} data warnings are still open.")
    if ind["unmatched_old_invoices"]:
        factor *= 0.95
    if blocking:
        score -= 40
        reason("lowers", "Blocking data problems remain, so no limit is suggested.")

    limit = None if blocking else int(ind["avg_monthly_revenue_last6"] * LIMIT_MONTHS_OF_SALES * factor // 10_000 * 10_000)
    confidence = "High" if score >= HIGH else "Medium" if score >= MEDIUM else "Low"
    return {"label": "initial", "suggested_limit_sar": limit, "confidence": confidence,
            "score": score, "reasons": reasons}
