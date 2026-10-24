"""Financing Readiness Platform (FRP) prototype: wholesaler and bank analyst screens."""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from frp.pipeline import run_pipeline

DATA = Path(__file__).parent / "data"
WHOLESALER, BANK = "Al-Noor Foods Trading", "Bank A"
STATUS = {"draft": "Draft", "needs_fixes": "Needs fixes", "ready": "Ready to submit",
          "submitted": "Submitted to bank", "info_requested": "Bank requested information",
          "approved": "Approved", "rejected": "Rejected"}

st.set_page_config(page_title="Financing Readiness Platform", layout="wide")


@st.cache_data(show_spinner="Cleaning data and running checks...")
def analyze(invoice_bytes: bytes, bank_bytes: bytes):
    return run_pipeline(BytesIO(invoice_bytes), BytesIO(bank_bytes))


# ------------------------------------------------------------------ state ---
for key, default in {"status": "draft", "inv_bytes": None, "bank_bytes": None, "uploader": 0,
                     "events": [], "info_request": None, "info_response": None}.items():
    st.session_state.setdefault(key, default)
s = st.session_state


def money(x):
    return f"SAR {x:,.0f}"


def log_event(who, text):
    s.events.append({"Time": datetime.now().strftime("%Y-%m-%d %H:%M"), "Who": who, "What": text})


def current_result():
    bank_bytes = s.bank_bytes or (DATA / "bank_statement.csv").read_bytes()
    return analyze(s.inv_bytes, bank_bytes)


def show_events():
    if s.events:
        st.subheader("Activity")
        st.dataframe(pd.DataFrame(s.events), hide_index=True)


def show_alerts(result):
    """Alerts with a drill-down to the invoices behind each one."""
    if not result["alerts"]:
        st.success("No problems found.")
    for a in result["alerts"]:
        (st.error if a["severity"] == "blocking" else st.warning)(
            ("Must fix: " if a["severity"] == "blocking" else "Review: ") + a["message"])
        if a["invoice_nos"] and "invoices" in result:
            with st.expander(f"Show the {len(a['invoice_nos'])} invoice(s) behind this"):
                inv = result["invoices"]
                t = inv[inv["invoice_no"].isin(a["invoice_nos"])][
                    ["source_row", "invoice_no", "issue_date", "buyer_raw", "total", "paid"]].copy()
                t["issue_date"] = t["issue_date"].dt.date
                st.dataframe(t.rename(columns={"source_row": "Excel row", "invoice_no": "Invoice",
                                               "issue_date": "Issue date", "buyer_raw": "Customer (as written)",
                                               "total": "Total (SAR)", "paid": "Matched to a bank payment"}),
                             hide_index=True)


# -------------------------------------------------------------- wholesaler ---
def load_sample(name):
    s.inv_bytes = (DATA / name).read_bytes()
    s.bank_bytes = (DATA / "bank_statement.csv").read_bytes()
    s.uploader += 1                       # resets the file pickers so the sample takes over


def wholesaler_view():
    st.title("Financing request")
    st.caption(f"{WHOLESALER}  |  Linked bank: {BANK}  |  Period: Oct 2025 to Sep 2026")

    if s.status in ("submitted", "approved", "rejected"):
        (st.success if s.status != "rejected" else st.error)(f"Status: {STATUS[s.status]}.")
        st.write("Your package was sent to the bank. It can no longer be edited.")
        show_events()
        return

    if s.status == "info_requested":
        st.warning(f"{BANK} asks for more information:")
        st.info(s.info_request)
        text = st.text_area("Your response")
        st.file_uploader("Attach a file (optional)", key="response_file")
        if st.button("Send response", type="primary", disabled=not text.strip()):
            s.info_response = text.strip()
            s.info_request = None
            s.status = "submitted"
            log_event("Wholesaler", f"Responded: {text.strip()}")
            st.rerun()
        show_events()
        return

    st.subheader("1. Upload your files")
    c1, c2 = st.columns(2)
    inv_file = c1.file_uploader("Invoices (Excel, 12 months)", type=["xlsx"], key=f"inv_{s.uploader}")
    bank_file = c2.file_uploader("Bank statement (CSV)", type=["csv"], key=f"bank_{s.uploader}")
    if inv_file:
        s.inv_bytes = inv_file.getvalue()
    if bank_file:
        s.bank_bytes = bank_file.getvalue()
    st.caption("No files at hand? Load a sample (with the sample bank statement):")
    b1, b2, _ = st.columns([1, 1, 2])
    if b1.button("Sample: invoices with problems", key="load_bad"):
        load_sample("invoices_with_issues.xlsx")
        st.rerun()
    if b2.button("Sample: corrected invoices", key="load_clean"):
        load_sample("invoices_clean.xlsx")
        st.rerun()

    if not s.inv_bytes:
        st.info("Upload your invoices to continue. If no bank statement is uploaded, the sample one is used.")
        return

    result = current_result()
    s.status = result["status"]
    blocking = [a for a in result["alerts"] if a["severity"] == "blocking"]
    warnings = [a for a in result["alerts"] if a["severity"] == "warning"]

    st.subheader("2. Check results")
    m1, m2, m3 = st.columns(3)
    if "invoices" in result:
        m1.metric("Invoices read", int((~result["invoices"]["is_duplicate"]).sum()))
    m2.metric("Must fix before sending", len(blocking))
    m3.metric("Warnings to review", len(warnings))
    show_alerts(result)
    if "invoices" not in result:
        return
    if result["cleaning_log"]:
        with st.expander(f"What FRP changed automatically ({len(result['cleaning_log'])} changes)"):
            st.caption("Only formatting fixes. Amounts are never changed and nothing is deleted.")
            st.dataframe(pd.DataFrame(result["cleaning_log"]).rename(columns={
                "invoice_no": "Invoice", "source_row": "Excel row", "field": "Field",
                "old": "Before", "new": "After", "rule": "Rule"}), hide_index=True)

    st.subheader("3. Preview of your standardized data")
    inv = result["invoices"]
    preview = inv[["invoice_no", "issue_date", "due_date", "buyer", "subtotal", "vat", "total"]].head(15).copy()
    preview["issue_date"], preview["due_date"] = preview["issue_date"].dt.date, preview["due_date"].dt.date
    st.dataframe(preview, hide_index=True)

    st.subheader("4. Submit")
    if blocking:
        st.error("Fix the issues marked 'Must fix', then upload the corrected file. "
                 "Try the 'corrected invoices' sample to see the next step.")
        return
    months = inv["issue_date"].dt.to_period("M").nunique()
    st.write(f"Ready to send to **{BANK}**: **{int((~inv['is_duplicate']).sum())} invoices** over "
             f"**{months} months**, with **{len(warnings)} open warning(s)** (the bank will see them).")
    agree = st.checkbox(f"I confirm this data is correct and I agree to share it with {BANK}.")
    if st.button("Submit to bank", type="primary", disabled=not agree):
        s.status = "submitted"
        log_event("Wholesaler", "Submitted the financing package.")
        st.rerun()


# -------------------------------------------------------------------- bank ---
def bank_view():
    st.title(f"{BANK}: financing applications")
    if s.status not in ("submitted", "info_requested", "approved", "rejected"):
        st.info("No submitted applications yet. Switch to the wholesaler role (sidebar) and submit one.")
        return

    result = current_result()
    ind, rec, inv = result["indicators"], result["recommendation"], result["invoices"]
    st.dataframe(pd.DataFrame([{"Wholesaler": WHOLESALER, "Status": STATUS[s.status],
                                "Invoices": ind["invoice_count"], "Period": "Oct 2025 to Sep 2026"}]),
                 hide_index=True)

    st.subheader("Merchant health")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Avg monthly revenue", money(ind["avg_monthly_revenue"]), help="Before VAT")
    k2.metric("Avg invoice value", money(ind["avg_invoice_value"]))
    k3.metric("Top buyer share", f"{ind['top_buyer']['share']:.0%}", help=ind["top_buyer"]["name"])
    k4.metric("Overdue rate", f"{ind['overdue_rate']:.1%}", help="Share of invoices already due that are unpaid")
    st.caption("Monthly revenue before VAT (SAR). Peaks before Ramadan, slower in summer.")
    st.bar_chart(pd.DataFrame(ind["revenue_by_month"]).set_index("month")["revenue"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Collection quality**")
        st.write(f"Paid invoices arrive on average **{ind['avg_days_late_when_paid']} days** after the due date.")
        st.dataframe(pd.DataFrame({"Days overdue": list(ind["overdue_aging_sar"]),
                                   "Unpaid (SAR)": [round(v) for v in ind["overdue_aging_sar"].values()]}),
                     hide_index=True)
    with right:
        st.markdown("**Buyer concentration**")
        uniq = inv[~inv["is_duplicate"]]
        top = uniq.groupby("buyer")["subtotal"].sum().sort_values(ascending=False).head(5)
        st.dataframe(pd.DataFrame({"Buyer": top.index, "Revenue (SAR)": top.round(0).values,
                                   "Share": (top / uniq["subtotal"].sum() * 100).round(1).astype(str).values + "%"}),
                     hide_index=True)
        st.write(f"Top 3 buyers: **{ind['top3_share']:.0%}** of revenue.")

    st.subheader("Data alerts")
    st.caption("The wholesaler saw these before submitting. Click a row group to check the invoices.")
    show_alerts(result)
    if result["cleaning_log"]:
        st.caption(f"FRP made {len(result['cleaning_log'])} automatic formatting changes "
                   "(for example, merging buyer names written in different ways).")

    st.subheader("Initial recommendation")
    with st.container(border=True):
        r1, r2 = st.columns(2)
        r1.metric("Suggested limit", money(rec["suggested_limit_sar"]) if rec["suggested_limit_sar"] else "None")
        r2.metric("Confidence", rec["confidence"])
        for r in rec["reasons"]:
            st.markdown((":green[Supports] " if r["effect"] == "supports" else ":orange[Lowers confidence] ") + r["text"])
        st.caption("Calculated by transparent rules from the figures above. It is a starting point; "
                   "the decision stays with the analyst.")

    st.subheader("Decision")
    if s.status in ("approved", "rejected"):
        st.success(f"Decision recorded: {STATUS[s.status]}.")
    elif s.status == "info_requested":
        st.info("Waiting for the wholesaler to respond to your request.")
    else:
        if s.info_response:
            st.info(f"Wholesaler's response: {s.info_response}")
        choice = st.radio("Your decision", ["Approve", "Reject", "Request more information"], horizontal=True)
        reason = st.text_area("Reason (required to reject or request information)")
        need_reason = choice != "Approve"
        if st.button("Record decision", type="primary", disabled=need_reason and not reason.strip()):
            if choice == "Approve":
                s.status = "approved"
            elif choice == "Reject":
                s.status = "rejected"
            else:
                s.status, s.info_request, s.info_response = "info_requested", reason.strip(), None
            log_event("Bank analyst", f"{choice}" + (f": {reason.strip()}" if reason.strip() else ""))
            st.rerun()
    show_events()


# -------------------------------------------------------------------- main ---
role = st.sidebar.radio("Demo role", ["Wholesaler", "Bank analyst"])
st.sidebar.caption("Demo only: real sign-in and separate accounts are out of scope.")
st.sidebar.markdown(f"**Application status:** {STATUS[s.status]}")
if st.sidebar.button("Reset demo"):
    for key in list(s.keys()):
        del s[key]
    st.rerun()

wholesaler_view() if role == "Wholesaler" else bank_view()
