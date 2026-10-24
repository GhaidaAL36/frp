"""One call that runs everything: load -> clean -> match payments -> checks -> indicators -> recommendation."""
from datetime import date

import pandas as pd

from .checks import run_checks
from .cleaning import load_invoices
from .indicators import compute_indicators, recommend
from .matching import match_payments


def run_pipeline(invoice_file, bank_csv, period_start=date(2025, 10, 1), period_end=date(2026, 9, 30)):
    expected = pd.period_range(period_start, period_end, freq="M")
    bank = pd.read_csv(bank_csv, parse_dates=["date"])
    loaded = load_invoices(invoice_file)
    if loaded["missing_columns"]:
        alerts = run_checks(None, {}, loaded["missing_columns"], expected, period_end)
        return {"status": "needs_fixes", "alerts": alerts, "cleaning_log": loaded["log"]}

    matched = match_payments(loaded["invoices"], bank)
    alerts = run_checks(matched, loaded["merged_names"], [], expected, period_end, bank)
    # repeated rows of the same invoice number are counted once in the indicators (and flagged above)
    unique = matched[~matched["is_duplicate"]].dropna(subset=["issue_date"])
    indicators = compute_indicators(unique, bank, expected, period_end)
    return {"status": "needs_fixes" if any(a["severity"] == "blocking" for a in alerts) else "ready",
            "alerts": alerts, "cleaning_log": loaded["log"], "indicators": indicators,
            "recommendation": recommend(indicators, alerts), "invoices": matched}
