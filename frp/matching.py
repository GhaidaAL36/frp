"""Match invoices to bank credits (one-to-one)."""
import re

import pandas as pd


def _alnum(text):
    return re.sub(r"[^a-z0-9\u0600-\u06FF]", "", str(text).lower())


def match_payments(invoices, bank):
    """A credit pays an invoice when: same amount (to the halala), credit date on or after the
    invoice date, and the buyer's name appears in the bank description."""
    credits = bank[bank["direction"] == "credit"].sort_values("date")
    pool = {}
    for _, c in credits.iterrows():
        pool.setdefault(int(round(c["amount"] * 100)), []).append((c["date"], _alnum(c["description"])))

    out = invoices.copy()
    out["paid"] = False
    out["payment_date"] = pd.NaT
    out["is_duplicate"] = out.duplicated("invoice_no", keep="first")   # a repeated row is never matched
    for i, inv in out.sort_values("issue_date").iterrows():
        if inv["is_duplicate"] or pd.isna(inv["total"]) or pd.isna(inv["issue_date"]):
            continue
        name = _alnum(inv["buyer"])
        candidates = pool.get(int(round(inv["total"] * 100)), [])
        for cand in candidates:
            if cand[0] >= inv["issue_date"] and name in cand[1]:
                out.at[i, "paid"] = True
                out.at[i, "payment_date"] = cand[0]
                candidates.remove(cand)
                break
    out["days_late"] = (out["payment_date"] - out["due_date"]).dt.days
    return out
