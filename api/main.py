"""Part 4: FastAPI service. All grouping and summing is done by the database (SQL);
Python only formats the answer.

Start it with:  uvicorn api.main:app --reload
Docs (auto-generated): http://127.0.0.1:8000/docs
"""
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from pipeline.db import get_engine

app = FastAPI(title="Retail Sales API", version="1.0")
engine = get_engine()

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM; anything else -> 422 automatically
MAX_LIMIT = 100


def _num(v) -> Optional[float]:
    return None if v is None else float(v)


def _day(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if isinstance(v, date) else str(v)[:10]


@app.get("/health")
def health():
    """Simple OK, plus whether the database connection works (503 if it does not)."""
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "ok", "database": "up"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "ok", "database": "down"})


@app.get("/customers/{customer_id}/summary")
def customer_summary(customer_id: str = Path(..., max_length=20)):
    """Country, region, first/last order date, number of invoices, total spend (GBP + USD)."""
    with engine.connect() as c:
        cust = c.execute(text(
            "SELECT c.customer_key, c.customer_id, co.country_name, co.region "
            "FROM dim_customer c JOIN dim_country co ON co.country_key = c.country_key "
            "WHERE c.customer_id = :cid AND c.is_placeholder = 0"), {"cid": customer_id.strip()}).first()
        if cust is None:
            raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
        agg = c.execute(text(
            "SELECT MIN(CASE WHEN f.is_cancellation = 0 THEN d.full_date END) AS first_order, "
            "       MAX(CASE WHEN f.is_cancellation = 0 THEN d.full_date END) AS last_order, "
            "       COUNT(DISTINCT CASE WHEN f.is_cancellation = 0 THEN f.invoice_no END) AS invoices, "
            "       ROUND(SUM(f.gross_gbp), 2) AS spend_gbp, ROUND(SUM(f.gross_usd), 2) AS spend_usd "
            "FROM fact_invoice_line f JOIN dim_date d ON d.date_key = f.date_key "
            "WHERE f.customer_key = :k AND f.is_revenue = 1"), {"k": cust.customer_key}).one()
    return {
        "customer_id": cust.customer_id,
        "country": cust.country_name,
        "region": cust.region,
        "first_order_date": _day(agg.first_order),
        "last_order_date": _day(agg.last_order),
        "invoice_count": int(agg.invoices or 0),
        "total_spend_gbp": _num(agg.spend_gbp) or 0.0,
        "total_spend_usd": _num(agg.spend_usd) or 0.0,
    }


@app.get("/products/top")
def top_products(
    month: str = Query(..., pattern=MONTH_PATTERN, description="YYYY-MM", examples=["2011-03"]),
    limit: int = Query(10, ge=1, le=MAX_LIMIT, description=f"1..{MAX_LIMIT}"),
):
    """Best-selling products in a month, by revenue in USD."""
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT p.stock_code, p.description, "
            "       SUM(CASE WHEN f.is_cancellation = 0 THEN f.quantity ELSE 0 END) AS units, "
            "       ROUND(SUM(f.gross_gbp), 2) AS revenue_gbp, ROUND(SUM(f.gross_usd), 2) AS revenue_usd "
            "FROM fact_invoice_line f "
            "JOIN dim_date d ON d.date_key = f.date_key "
            "JOIN dim_product p ON p.product_key = f.product_key "
            "WHERE f.is_revenue = 1 AND d.month_key = :m "
            "GROUP BY p.stock_code, p.description "
            "ORDER BY SUM(f.gross_usd) DESC, p.stock_code "
            "LIMIT :lim"), {"m": month, "lim": limit}).all()
    return {"month": month, "limit": limit, "products": [
        {"rank": i, "stock_code": r.stock_code, "description": r.description,
         "units_sold": int(r.units or 0),
         "revenue_gbp": _num(r.revenue_gbp), "revenue_usd": _num(r.revenue_usd)}
        for i, r in enumerate(rows, 1)]}


@app.get("/kpis/monthly")
def monthly_kpis(
    start: str = Query(..., pattern=MONTH_PATTERN, description="YYYY-MM", examples=["2010-01"]),
    end: str = Query(..., pattern=MONTH_PATTERN, description="YYYY-MM", examples=["2010-12"]),
    region: Optional[str] = Query(None, max_length=60, description="optional, e.g. 'Western Europe'"),
):
    """Per month: invoices, units sold, revenue in GBP and USD (optionally for one region)."""
    if start > end:  # 'YYYY-MM' strings sort in date order
        raise HTTPException(status_code=422, detail="start must not be after end")
    params = {"s": start, "e": end}
    region_join, region_where = "", ""
    with engine.connect() as c:
        if region:
            ok = c.execute(text("SELECT 1 FROM dim_country WHERE region = :r LIMIT 1"), {"r": region}).first()
            if ok is None:
                regions = [r[0] for r in c.execute(text("SELECT DISTINCT region FROM dim_country ORDER BY region"))]
                raise HTTPException(status_code=422, detail=f"Unknown region. Valid regions: {regions}")
            region_join = "JOIN dim_country co ON co.country_key = f.country_key"
            region_where = "AND co.region = :r"
            params["r"] = region
        rows = c.execute(text(
            "SELECT d.month_key, "
            "       COUNT(DISTINCT CASE WHEN f.is_cancellation = 0 THEN f.invoice_no END) AS invoices, "
            "       COALESCE(SUM(CASE WHEN f.is_cancellation = 0 THEN f.quantity ELSE 0 END), 0) AS units, "
            "       ROUND(SUM(f.gross_gbp), 2) AS revenue_gbp, ROUND(SUM(f.gross_usd), 2) AS revenue_usd "
            "FROM fact_invoice_line f "
            "JOIN dim_date d ON d.date_key = f.date_key "
            f"{region_join} "
            f"WHERE f.is_revenue = 1 AND d.month_key BETWEEN :s AND :e {region_where} "
            "GROUP BY d.month_key ORDER BY d.month_key"), params).all()
    return {"start": start, "end": end, "region": region, "months": [
        {"month": r.month_key, "invoices": int(r.invoices), "units_sold": int(r.units),
         "revenue_gbp": _num(r.revenue_gbp), "revenue_usd": _num(r.revenue_usd)} for r in rows]}


@app.get("/data-quality/summary")
def data_quality_summary():
    """How many issues were logged, grouped by rule."""
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT rule, issue_type, action, COUNT(*) AS n FROM data_quality_issue "
            "GROUP BY rule, issue_type, action ORDER BY rule, issue_type")).all()
    by_rule: dict = {}
    for r in rows:
        entry = by_rule.setdefault(r.rule, {"rule": r.rule, "issues": 0, "breakdown": []})
        entry["issues"] += int(r.n)
        entry["breakdown"].append({"issue_type": r.issue_type, "action": r.action, "count": int(r.n)})
    return {"total_issues": sum(e["issues"] for e in by_rule.values()), "by_rule": list(by_rule.values())}
