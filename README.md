# Financing Readiness Platform (FRP)

A prototype that turns a wholesaler's invoices and bank statement into a clean, checked package, so a bank analyst can reach a financing decision from one page instead of reviewing raw files.

**Live demo:** https://frpdemo.streamlit.app/

## What it does

**Wholesaler screen**
1. Upload 12 months of invoices (Excel) and a bank statement (CSV), or load a built-in sample.
2. FRP standardizes the data, runs checks, and shows alerts: *Must fix* (blocks sending) or *Review* (warning).
3. Every automatic change is listed; amounts are never changed and nothing is deleted.
4. The wholesaler confirms and submits to the linked bank.

**Bank analyst screen**
1. One page: revenue trend, average invoice value, collection quality, buyer concentration.
2. Data alerts, each opening the invoices behind it.
3. An initial recommendation (suggested limit, confidence, reasons).
4. Decision: approve, reject, or request more information (the wholesaler replies and the request returns to the bank).

Switch between the two with the role selector in the sidebar.

## Try it in two minutes
1. Wholesaler: click **Sample: invoices with problems**. You see one blocking alert (July is missing), warnings (duplicates, buyer names merged, 6 invoices with no bank payment), and Submit is not offered.
2. Click **Sample: corrected invoices**. One warning remains; tick the consent box and submit.
3. Switch to **Bank analyst**: review the page and request more information, then switch back to answer, then approve.

## Run it locally
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python generate_data.py     # optional: the data/ folder is already included
python test_pipeline.py     # checks every planted problem is caught
streamlit run app.py
```

## Sample data (all made up)
The wholesaler, buyers and suppliers are fictional. `generate_data.py` creates the files with a fixed seed.

| File | Content |
|---|---|
| `data/invoices_clean.xlsx` | 2,766 invoices, Oct 2025 to Sep 2026, SAR 15.6M before VAT |
| `data/invoices_with_issues.xlsx` | Same data after planting problems |
| `data/bank_statement.csv` | 2,624 movements (customer payments, payroll, rent, suppliers, VAT) |
| `data/ground_truth.json` | What was planted; used by the tests |

**Al-Noor Foods Trading**: a food wholesaler in Riyadh with about 33 buyers, busy before Ramadan (Jan to Feb 2026) and slower in summer.

**Planted in the "with issues" file:** July 2026 missing; two invoices that appear twice; the same buyer written in different ways.

**Built into both files (business risks, not file errors):** one buyer is 39.5% of revenue (top 3: 58%); 6 large invoices (SAR 52,118) have no matching bank payment; the bank balance gets as low as SAR 149k.

## How the pieces fit
| Module | Job |
|---|---|
| `frp/cleaning.py` | Read the Excel file, map column names, fix formatting, merge similar buyer names, log every change |
| `frp/matching.py` | Match invoices to bank payments (amount, date, buyer name) |
| `frp/checks.py` | Alerts: missing months, duplicates, unusual amounts, VAT, impossible dates, no bank payment |
| `frp/indicators.py` | Indicators and the rule-based recommendation |
| `frp/pipeline.py` | Runs everything in one call |
| `app.py` | Streamlit screens |

All figures are computed in code and no model estimates them, so each number can be traced to invoices. Results on the sample data: the problem file is blocked; the corrected file gets a suggested limit of SAR 890,000 with Medium confidence (one buyer at 40% and six unpaid large invoices lower it).

## Assumptions
- Revenue is counted before VAT; all amounts are in SAR; payment terms are 30 days.
- A wholesaler is linked in advance to a bank it already has an agreement with; FRP is only the intermediary.
- Bank statements are CSV. Reading PDF statements is out of scope.
- Payments match invoices one-to-one by exact total, date and buyer name. Partial or combined payments are out of scope.
- An invoice is flagged when it is over 75 days old with no matching payment.
- Repeated rows of the same invoice number are counted once in the indicators and flagged for the wholesaler.
- Recommendation rules (thresholds are my assumptions; a bank would set its own):
  - Buyer share above 35%, overdue rate above 5%, revenue variation above 30%, lowest balance below 10% of monthly sales: each lowers confidence.
  - Suggested limit = average of the last 6 months' sales, reduced by those risks.
  - Confidence: High at 80 or more, Medium at 50 or more, otherwise Low.
  - No limit is suggested while a blocking problem remains.
- Weekend is Friday and Saturday.

## Not included
- The REST API and data model from the technical spec are designs only. The prototype calls the pipeline directly.
- No sign-in, database or email notifications; state lives in the browser session and resets on reload.
- Automatic pulling from accounting systems and the Qawafel operations view.
- Only one bank (Bank A) in the demo.
