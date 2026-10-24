"""Load an invoice Excel file, standardize it, and record every automatic change."""
import re
from difflib import SequenceMatcher

import pandas as pd

# Different wholesalers name their columns differently; map them to one standard.
COLUMN_ALIASES = {
    "invoice_no": ["invoice no", "invoice number", "invoice #", "inv no", "رقم الفاتورة"],
    "issue_date": ["issue date", "invoice date", "date", "تاريخ الفاتورة"],
    "due_date": ["due date", "payment due", "تاريخ الاستحقاق"],
    "buyer": ["customer", "customer name", "client", "buyer", "العميل"],
    "subtotal": ["subtotal (sar)", "subtotal", "amount excl vat", "amount (excl. vat)", "المبلغ قبل الضريبة"],
    "vat": ["vat 15% (sar)", "vat", "vat amount", "الضريبة"],
    "total": ["total (sar)", "total", "total amount", "الإجمالي"],
}
REQUIRED = ["invoice_no", "issue_date", "buyer", "subtotal", "total"]
DEFAULT_TERMS_DAYS = 30
ABBREVIATIONS = {"mkt": "market", "mrkt": "market", "co": "", "company": "", "ltd": "", "llc": ""}
NAME_SIMILARITY = 0.90


def _header_key(header):
    return re.sub(r"\s+", " ", str(header).strip().lower())


def _to_number(series):
    if series.dtype == object:
        series = series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(series, errors="coerce")


def _name_key(name):
    tokens = re.findall(r"[a-z0-9\u0600-\u06FF]+", name.lower())
    return "".join(ABBREVIATIONS.get(t, t) for t in tokens)


def normalize_buyers(df, log):
    """Merge buyer names that look like the same business. Returns (df, {kept_name: [merged names]})."""
    kept = []                                   # (key, name), most frequent spelling first
    mapping = {}
    for name in df["buyer"].value_counts().index:
        key = _name_key(name)
        match = next((n for k, n in kept
                      if k == key or SequenceMatcher(None, k, key).ratio() >= NAME_SIMILARITY), None)
        if match is None:
            kept.append((key, name))
            match = name
        mapping[name] = match
    merged = {}
    for name, target in mapping.items():
        if name != target:
            merged.setdefault(target, []).append(name)
    new = df["buyer"].map(mapping)
    for i in df.index[new != df["buyer"]]:
        log.append({"invoice_no": df.at[i, "invoice_no"], "source_row": int(df.at[i, "source_row"]),
                    "field": "buyer", "old": df.at[i, "buyer"], "new": new[i],
                    "rule": "merge_similar_buyer_names"})
    df["buyer"] = new
    return df, merged


def load_invoices(source):
    """Returns {"invoices", "log", "missing_columns", "merged_names"}."""
    raw = pd.read_excel(source)
    raw["source_row"] = raw.index + 2           # row number in the Excel file (header is row 1)
    lookup = {alias: std for std, aliases in COLUMN_ALIASES.items() for alias in aliases}
    df = raw.rename(columns={c: lookup[_header_key(c)] for c in raw.columns if _header_key(c) in lookup})
    df = df[[c for c in ["source_row", *COLUMN_ALIASES] if c in df.columns]].copy()
    missing = [c for c in REQUIRED if c not in df.columns]
    log = []
    if missing:
        return {"invoices": df, "log": log, "missing_columns": missing, "merged_names": {}}

    for col in ("issue_date", "due_date"):
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ("subtotal", "vat", "total"):
        if col in df:
            df[col] = _to_number(df[col])
    if "due_date" not in df:                    # assumption recorded in the log
        df["due_date"] = df["issue_date"] + pd.Timedelta(days=DEFAULT_TERMS_DAYS)
        log.append({"invoice_no": None, "source_row": None, "field": "due_date", "old": None,
                    "new": f"issue date + {DEFAULT_TERMS_DAYS} days", "rule": "assume_payment_terms"})

    for col in ("invoice_no", "buyer"):         # safe formatting fixes only; amounts are never changed
        original = df[col].astype(str)
        trimmed = original.str.strip().str.replace(r"\s+", " ", regex=True)
        for i in df.index[trimmed != original]:
            log.append({"invoice_no": df.at[i, "invoice_no"], "source_row": int(df.at[i, "source_row"]),
                        "field": col, "old": original[i], "new": trimmed[i], "rule": "trim_whitespace"})
        df[col] = trimmed
    df["buyer_raw"] = df["buyer"]
    df, merged = normalize_buyers(df, log)
    return {"invoices": df, "log": log, "missing_columns": [], "merged_names": merged}
