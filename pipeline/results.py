"""Builds RESULTS.md from the database + the stats saved by the pipeline run.
Every number is computed in SQL (rounded to 2 decimals only at the very end)."""
import json
from datetime import date

from sqlalchemy import text

from .config import RESULTS_MD, STATS_JSON


def _one(conn, sql, **p):
    return conn.execute(text(sql), p).all()


def compute(engine) -> dict:
    with engine.connect() as c:
        tot = _one(c, "SELECT ROUND(SUM(gross_gbp),2), ROUND(SUM(gross_usd),2) "
                      "FROM fact_invoice_line WHERE is_revenue = 1")[0]
        sales = _one(c, "SELECT ROUND(SUM(gross_gbp),2), ROUND(SUM(gross_usd),2) "
                        "FROM fact_invoice_line WHERE is_revenue = 1 AND is_cancellation = 0")[0]
        dec = _one(c, "SELECT ROUND(SUM(f.gross_gbp),2), ROUND(SUM(f.gross_usd),2) "
                      "FROM fact_invoice_line f JOIN dim_date d ON d.date_key = f.date_key "
                      "WHERE f.is_revenue = 1 AND d.month_key = '2010-12'")[0]
        top = _one(c, "SELECT p.stock_code, p.description, ROUND(SUM(f.gross_usd),2) AS usd, "
                      "ROUND(SUM(f.gross_gbp),2) AS gbp "
                      "FROM fact_invoice_line f JOIN dim_date d ON d.date_key = f.date_key "
                      "JOIN dim_product p ON p.product_key = f.product_key "
                      "WHERE f.is_revenue = 1 AND d.month_key = '2011-03' "
                      "GROUP BY p.stock_code, p.description ORDER BY SUM(f.gross_usd) DESC, p.stock_code "
                      "LIMIT 5")
        cust = _one(c, "SELECT COUNT(*) FROM dim_customer WHERE is_placeholder = 0")[0][0]
        dq = _one(c, "SELECT rule, issue_type, action, COUNT(*) FROM data_quality_issue "
                     "GROUP BY rule, issue_type, action ORDER BY rule, issue_type")
        fact_rows = _one(c, "SELECT COUNT(*) FROM fact_invoice_line")[0][0]
    return {"total": tot, "sales_only": sales, "dec2010": dec, "top": top,
            "customers": cust, "dq": dq, "fact_rows": fact_rows}


def _money(v):
    return "n/a" if v is None else f"{float(v):,.2f}"


def write_results_md(engine) -> str:
    s = json.loads(STATS_JSON.read_text())
    r = compute(engine)
    by_rule: dict[str, int] = {}
    for rule, _t, _a, n in r["dq"]:
        by_rule[rule] = by_rule.get(rule, 0) + n

    L = []
    a = L.append
    a("# RESULTS\n")
    a(f"_Generated automatically by `python -m pipeline.run` on {date.today()}. "
      "Money is summed in SQL and rounded to 2 decimals only at the end._\n")
    a("**Revenue definition (see ASSUMPTIONS.md, R2/R4/R5):** product lines only, "
      "free samples (price 0) and stock write-offs excluded, cancellation lines (invoice starts with C) "
      "**included as negatives**, so it is net of cancellations. The sales-only figure "
      "(cancellations left out) is shown as well.\n")
    a("## 1. Rows\n")
    a("| What | Number |\n|---|---:|")
    a(f"| Rows read in total (both sheets) | {s['rows_read']:,} |")
    for sheet, n in s["rows_read_by_sheet"].items():
        a(f"| &nbsp;&nbsp;of which sheet `{sheet}` | {n:,} |")
    a(f"| R1 exact duplicates removed | {s['r1_duplicates_removed']:,} |")
    a(f"| Unreadable rows rejected (not an official rule) | {s['unreadable_rows_rejected']:,} |")
    a(f"| Rejected by R5 (negative price) | {s['r5_negative_price_rejected']:,} |")
    a(f"| Rows rejected by R7 (no earlier FX rate) | {s['r7_rows_before'] - s['r7_rows_after']:,} |")
    a(f"| Rows loaded into `fact_invoice_line` | {r['fact_rows']:,} |\n")
    a("## 2. R2 - cancellations vs negative quantities\n")
    a("| What | Number |\n|---|---:|")
    a(f"| Cancellation lines (invoice starts with C) | {s['r2_cancellation_lines']:,} |")
    a(f"| Negative-quantity lines that are NOT cancellations (stock write-offs) | {s['r2_negative_qty_not_cancellation']:,} |\n")
    a("## 3. R4 and R5 - rows excluded from revenue\n")
    a("| What | Number |\n|---|---:|")
    a(f"| R4 non-product rows (kept, marked, no product revenue) | {s['r4_non_product_rows']:,} |")
    a(f"| R5 zero-price rows (kept, no revenue) | {s['r5_zero_price_rows']:,} |")
    a(f"| R5 negative-price rows (rejected) | {s['r5_negative_price_rejected']:,} |")
    a(f"| Overlap: R4 rows that also have price 0 | {s['r4_and_zero_price_overlap']:,} |")
    a(f"| Overlap: R4 rows that also have a negative price | {s['r4_and_negative_price_overlap']:,} |\n")
    a("## 4. Customers\n")
    a(f"Distinct customers (placeholder `GUEST` not counted): **{r['customers']:,}**\n")
    a("## 5. Revenue\n")
    a("| Period | GBP | USD |\n|---|---:|---:|")
    a(f"| Whole period (net of cancellations) | {_money(r['total'][0])} | {_money(r['total'][1])} |")
    a(f"| Whole period (sales only, cancellations left out) | {_money(r['sales_only'][0])} | {_money(r['sales_only'][1])} |")
    a(f"| December 2010 (net of cancellations) | {_money(r['dec2010'][0])} | {_money(r['dec2010'][1])} |\n")
    a("## 6. Top 5 products by USD revenue, March 2011\n")
    a("| # | Stock code | Description | USD | GBP |\n|---:|---|---|---:|---:|")
    for i, (code, desc, usd, gbp) in enumerate(r["top"], 1):
        a(f"| {i} | {code} | {desc} | {_money(usd)} | {_money(gbp)} |")
    a("\n## 7. R7 check\n")
    a(f"Rows before FX step: {s['r7_rows_before']:,}; after: {s['r7_rows_after']:,} "
      f"(a plain join would have lost the weekend rows). "
      f"Lines that used an earlier day's rate (weekends/holidays): {s['r7_rows_using_earlier_rate']:,}.\n")
    a("## 8. Data-quality issues per rule\n")
    a("| Rule | Issues logged |\n|---|---:|")
    for rule in sorted(by_rule):
        a(f"| {rule} | {by_rule[rule]:,} |")
    a(f"| **Total** | **{sum(by_rule.values()):,}** |\n")
    a("Breakdown:\n")
    a("| Rule | Type | Action | Count |\n|---|---|---|---:|")
    for rule, t, act, n in r["dq"]:
        a(f"| {rule} | {t} | {act} | {n:,} |")
    md = "\n".join(L) + "\n"
    RESULTS_MD.write_text(md)
    return md
