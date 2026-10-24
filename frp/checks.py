"""Data-quality checks. Each alert: type, severity (blocking | warning), message, invoice_nos.
Checks only flag; they never change or delete data."""
import numpy as np
import pandas as pd

VAT_RATE = 0.15
NO_PAYMENT_AFTER_DAYS = 75        # an invoice this old with no matching payment is flagged
OUTLIER_IQR_FACTOR = 3.0


def _alert(type_, severity, message, invoice_nos=()):
    return {"type": type_, "severity": severity, "message": message,
            "invoice_nos": sorted({str(n) for n in invoice_nos})}


def _rows(frame):
    return ", ".join(str(int(r)) for r in frame["source_row"])


def run_checks(matched, merged_names, missing_columns, expected_months, as_of, bank=None):
    as_of = pd.Timestamp(as_of)
    if missing_columns:
        return [_alert("missing_columns", "blocking",
                       "Required columns not found: " + ", ".join(missing_columns))]
    inv, alerts = matched, []

    bad_dates = inv[inv["issue_date"].isna()]
    if not bad_dates.empty:
        alerts.append(_alert("invalid_date", "blocking",
                             f"{len(bad_dates)} rows have an unreadable issue date (rows {_rows(bad_dates)})",
                             bad_dates["invoice_no"]))
    inv = inv.dropna(subset=["issue_date"])

    # 1. Missing months (the bank statement can confirm that money kept coming in)
    present = set(inv["issue_date"].dt.to_period("M"))
    for month in expected_months:
        if month not in present:
            hint = ""
            if bank is not None:
                n = int(((bank["direction"] == "credit") & (bank["date"].dt.to_period("M") == month)).sum())
                if n:
                    hint = f" The bank statement shows {n} customer payments received in that month."
            alerts.append(_alert("missing_month", "blocking", f"No invoices found for {month}.{hint}"))

    # 2. Duplicates
    for no, g in inv[inv.duplicated("invoice_no", keep=False)].groupby("invoice_no"):
        alerts.append(_alert("duplicate_invoice", "warning",
                             f"Invoice {no} appears {len(g)} times (rows {_rows(g)}).", [no]))
    same = inv.duplicated(["buyer", "issue_date", "total"], keep=False) & ~inv.duplicated("invoice_no", keep=False)
    if same.any():
        alerts.append(_alert("possible_duplicate", "warning",
                             f"{int(same.sum())} invoices share buyer, date and amount but have different numbers.",
                             inv.loc[same, "invoice_no"]))

    # 3. Unusual amounts (outliers on a log scale)
    logs = np.log(inv["subtotal"].clip(lower=1))
    q1, q3 = logs.quantile(0.25), logs.quantile(0.75)
    unusual = inv[logs > q3 + OUTLIER_IQR_FACTOR * (q3 - q1)]
    if not unusual.empty:
        alerts.append(_alert("unusual_amount", "warning",
                             f"{len(unusual)} invoices are unusually large compared with the rest "
                             f"(rows {_rows(unusual)}).", unusual["invoice_no"]))

    # 4. VAT and totals
    if "vat" in inv:
        wrong = inv[((inv["vat"] - (inv["subtotal"] * VAT_RATE).round(2)).abs() > 0.05)
                    | ((inv["total"] - (inv["subtotal"] + inv["vat"])).abs() > 0.05)]
        if not wrong.empty:
            alerts.append(_alert("vat_mismatch", "warning",
                                 f"{len(wrong)} invoices where VAT is not 15% or the total does not add up "
                                 f"(rows {_rows(wrong)}).", wrong["invoice_no"]))

    # 5. Dates that cannot be right
    odd = inv[(inv["issue_date"] > as_of) | (inv["due_date"] < inv["issue_date"])]
    if not odd.empty:
        alerts.append(_alert("impossible_date", "warning",
                             f"{len(odd)} invoices have a future issue date or a due date before the issue "
                             f"date (rows {_rows(odd)}).", odd["invoice_no"]))

    # 6. Buyer names that were merged (confirm with the wholesaler)
    if merged_names:
        groups = "; ".join(f"{', '.join(v)} -> {k}" for k, v in merged_names.items())
        alerts.append(_alert("buyer_name_variants", "warning",
                             f"Buyer names that look like the same business were merged: {groups}."))

    # 7. Old invoices with no matching bank payment
    old = inv[(~inv["paid"]) & (~inv["is_duplicate"]) & (inv["issue_date"] <= as_of - pd.Timedelta(days=NO_PAYMENT_AFTER_DAYS))]
    if not old.empty:
        alerts.append(_alert("no_bank_match", "warning",
                             f"{len(old)} invoices (SAR {old['total'].sum():,.0f}) issued more than "
                             f"{NO_PAYMENT_AFTER_DAYS} days ago have no matching bank payment: unpaid, paid "
                             f"another way, or not genuine.", old["invoice_no"]))

    return sorted(alerts, key=lambda a: a["severity"] != "blocking")
