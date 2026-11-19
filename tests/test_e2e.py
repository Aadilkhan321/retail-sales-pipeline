"""End-to-end test: sample workbook -> pipeline -> database -> API.

Runs on SQLite so anyone can run `pytest` without installing MySQL. The SQL used is
plain, portable SQL, and the MySQL version is created from the same table definitions.
"""
import importlib
import json
import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from pipeline import config, db, run
from tests.make_sample_data import build

warnings.filterwarnings("ignore", message=".*does \\*not\\* support Decimal.*")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    xlsx = build(tmp / "sample.xlsx")
    url = f"sqlite:///{tmp / 'retail.db'}"
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    mp.setattr(config, "STATS_JSON", tmp / "stats.json")
    mp.setattr(config, "RESULTS_MD", tmp / "RESULTS.md")
    for mod in ("pipeline.results", "pipeline.run"):
        importlib.reload(importlib.import_module(mod))
    args = ["--excel", str(xlsx), "--raw-dir", str(tmp / "raw")]
    importlib.import_module("pipeline.run").main(args)
    yield {"tmp": tmp, "args": args, "engine": db.get_engine(url)}
    mp.undo()
    for mod in ("pipeline.results", "pipeline.run"):
        importlib.reload(importlib.import_module(mod))


@pytest.fixture(scope="module")
def client(env):
    import api.main
    importlib.reload(api.main)
    return TestClient(api.main.app)


def scalar(env, sql):
    with env["engine"].connect() as c:
        return c.execute(text(sql)).scalar()


def test_counts_match_hand_calculation(env):
    s = json.loads((env["tmp"] / "stats.json").read_text())
    assert s["rows_read"] == 20
    assert s["r1_duplicates_removed"] == 2          # 1 inside sheet 1 + 1 across the two sheets
    assert s["r2_cancellation_lines"] == 2
    assert s["r2_negative_qty_not_cancellation"] == 2
    assert s["r3_rows_without_customer_id"] == 6
    assert s["r4_non_product_rows"] == 4            # POST, m, DOT, TEST001 (B is not in the list)
    assert s["r5_zero_price_rows"] == 2
    assert s["r5_negative_price_rejected"] == 1
    assert s["r7_rows_before"] == s["r7_rows_after"] == 17   # weekend rows not lost
    assert scalar(env, "SELECT COUNT(*) FROM fact_invoice_line") == 17


def test_raw_audit_files_are_saved(env):
    files = sorted(p.name for p in (env["tmp"] / "raw").glob("*.csv"))
    assert files == ["raw_year_2009_2010.csv", "raw_year_2010_2011.csv"]


def test_rerun_does_not_double_the_rows(env):
    before = scalar(env, "SELECT COUNT(*) FROM fact_invoice_line")
    dq_before = scalar(env, "SELECT COUNT(*) FROM data_quality_issue")
    importlib.import_module("pipeline.run").main(env["args"])
    assert scalar(env, "SELECT COUNT(*) FROM fact_invoice_line") == before
    assert scalar(env, "SELECT COUNT(*) FROM data_quality_issue") == dq_before


def test_weekend_rows_use_the_earlier_rate(env):
    with env["engine"].connect() as c:
        rows = c.execute(text(
            "SELECT invoice_no, fx_rate_date FROM fact_invoice_line "
            "WHERE invoice_no IN ('489442','500002','500003') ORDER BY invoice_no")).all()
    got = {r[0]: str(r[1])[:10] for r in rows}
    assert got == {"489442": "2009-12-04", "500002": "2010-12-03", "500003": "2010-12-03"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "up"}


def test_customer_summary_ok_and_404(client):
    r = client.get("/customers/15000/summary")
    assert r.status_code == 200
    j = r.json()
    assert j["country"] == "United Kingdom" and j["region"] == "UK & Ireland"
    assert j["invoice_count"] == 2 and j["first_order_date"] == "2010-12-03"
    assert j["total_spend_gbp"] == pytest.approx(15 * 2.55)
    assert client.get("/customers/99999/summary").status_code == 404
    assert client.get("/customers/GUEST/summary").status_code == 404   # placeholder is not a customer


def test_top_products_and_validation(client):
    r = client.get("/products/top", params={"month": "2011-03", "limit": 10})
    assert r.status_code == 200
    top = r.json()["products"]
    assert [p["stock_code"] for p in top] == ["84879", "22960"]   # postage/test codes excluded
    assert client.get("/products/top", params={"month": "2011-3"}).status_code == 422
    assert client.get("/products/top", params={"month": "2011-13"}).status_code == 422
    assert client.get("/products/top", params={"month": "2011-03", "limit": 100000}).status_code == 422
    assert client.get("/products/top", params={"month": "2011-03", "limit": 0}).status_code == 422


def test_monthly_kpis(client):
    r = client.get("/kpis/monthly", params={"start": "2011-03", "end": "2011-03"})
    m = r.json()["months"][0]
    assert m["month"] == "2011-03" and m["invoices"] == 2
    assert m["units_sold"] == 120                                   # cancellation units not counted as sold
    assert m["revenue_gbp"] == pytest.approx(100 * 1.69 + 20 * 3.0 - 10 * 1.69)  # net of cancellation
    r = client.get("/kpis/monthly", params={"start": "2011-03", "end": "2011-03", "region": "Unknown"})
    assert r.json()["months"][0]["invoices"] == 1                   # 'European Community' = Unknown
    assert client.get("/kpis/monthly", params={"start": "2011-03", "end": "2011-01"}).status_code == 422
    assert client.get("/kpis/monthly", params={"start": "bad", "end": "2011-01"}).status_code == 422
    assert client.get("/kpis/monthly", params={"start": "2011-01", "end": "2011-03", "region": "Mars"}).status_code == 422


def test_data_quality_summary(client):
    j = client.get("/data-quality/summary").json()
    rules_seen = {e["rule"]: e["issues"] for e in j["by_rule"]}
    assert rules_seen["R1"] == 2 and rules_seen["R5"] == 3
    assert j["total_issues"] == sum(rules_seen.values())
