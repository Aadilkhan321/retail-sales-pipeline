# Retail Sales Pipeline: ETL into MySQL, served through FastAPI

Reads the *Online Retail II* Excel workbook (two sheets), cleans it with eight rules (R1–R8),
loads a small star schema into MySQL, and serves the numbers through a FastAPI service.

```
Excel (2 sheets) ──► data/raw/*.csv (untouched audit copy)
                 └─► clean R1..R8 ──► MySQL star schema ──► FastAPI
                                          └─ data_quality_issue (every dropped / changed / flagged row)
```

| Document | What is in it |
|---|---|
| `README.md` | this file: setup, run, API examples |
| `ASSUMPTIONS.md` | every decision I made, by rule number, plus oddities I noticed in the brief |
| `RESULTS.md` | the requested numbers (written by the pipeline from the real data) |
| `sql/schema.sql` | the `CREATE TABLE` statements |

## 1. Requirements
- Python 3.10 or newer
- MySQL 8 (a ready-made one is in `docker-compose.yml`)
- About 4 GB of free RAM for the full workbook (about 1 million rows)

## 2. Set up

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**MySQL.** Either use Docker:

```bash
docker compose up -d                 # MySQL 8, user root / password, database "retail"
```

or use your own MySQL and tell the project how to reach it (the database itself is created for you):

```bash
export DATABASE_URL="mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/retail"
```
The default, if you set nothing, is `mysql+pymysql://root:password@127.0.0.1:3306/retail`.

**Data.** Download *Online Retail II* from
<https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci> and save it in `data/`
(do not edit it). Kaggle gives `online_retail_II.csv`; the original UCI version is an Excel workbook
(`online_retail_II.xlsx`, two sheets). Both work. The three reference CSVs are already in `data/reference/`.

## 3. Run the pipeline (one command)

```bash
python -m pipeline.run --input data/online_retail_II.csv      # or ... --input data/online_retail_II.xlsx
```

It takes a few minutes (reading and loading about 1 million rows). It will:

1. read both sheets (a CSV is split back into the two sheets) and write them unchanged to `data/raw/raw_year_2009_2010.csv` and `raw_year_2010_2011.csv`;
2. apply R1–R8 and log every issue;
3. re-create the tables and load them (so **running it twice does not double the rows**);
4. write `RESULTS.md` with all the requested numbers.

Try it in seconds on a tiny fake workbook (it contains every messy case):

```bash
python -m pipeline.run --input data/sample/sample_retail.xlsx
```

## 4. Start the API

```bash
uvicorn api.main:app --reload
```
Interactive docs: <http://127.0.0.1:8000/docs>

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/customers/12346/summary
curl "http://127.0.0.1:8000/products/top?month=2011-03&limit=5"
curl "http://127.0.0.1:8000/kpis/monthly?start=2010-01&end=2010-12&region=Western%20Europe"
curl http://127.0.0.1:8000/data-quality/summary
```

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status":"ok","database":"up"}` (HTTP 503 when the database is down) |
| `GET /customers/{customer_id}/summary` | country, region, first/last order date, invoice count, total spend GBP + USD. 404 if unknown |
| `GET /products/top?month=YYYY-MM&limit=10` | top products by USD revenue. Bad month → 422. `limit` must be 1–100 |
| `GET /kpis/monthly?start=YYYY-MM&end=YYYY-MM&region=` | per month: invoices, units, revenue GBP + USD. Bad month, `start > end` or unknown region → 422 |
| `GET /data-quality/summary` | issue counts grouped by rule |

All grouping and summing is done in SQL (`GROUP BY`, `SUM`, `COUNT(DISTINCT …)`); Python only formats the result.

## 5. Tests

```bash
pytest -q
```
- `tests/test_rules.py`: unit tests for the rules, with the most care on **R2** (C-prefix vs negative quantity) and **R7** (weekend rates, never a later rate, no lost rows).
- `tests/test_e2e.py`: runs the whole pipeline on the sample workbook, checks hand-calculated counts, checks a re-run does not duplicate, and calls every API endpoint (including 404 / 422 cases).

The tests run on SQLite so they need no MySQL; the same table definitions generate the MySQL schema.

## 6. Project layout

```
pipeline/   config.py  extract.py  rules.py  db.py  load.py  results.py  run.py  make_schema.py
api/        main.py
tests/      test_rules.py  test_e2e.py  make_sample_data.py
sql/        schema.sql
data/       reference/ (3 CSVs)   raw/ (audit copy, written by the pipeline)   sample/
```

## 7. Database design (star schema)

- `dim_date`, `dim_country`, `dim_customer` (incl. the `GUEST` placeholder), `dim_product`
- `fact_invoice_line`: one row per kept invoice line, foreign keys to all four dimensions, money as `DECIMAL`, dates as `DATE`/`DATETIME`, the FX rate and its source date, and flag columns (`is_cancellation`, `is_stock_writeoff`, `is_non_product`, `is_free_sample`, `is_revenue`)
- `data_quality_issue`: one row per removed / rejected / corrected / flagged row
- Indexes on the fact table for the API's queries: date, customer, (product, date), country, invoice; plus a unique key on (sheet, source row)

## 8. Use of AI tools
I used an AI assistant (Claude) to help write and review parts of this code and these documents. I have read the code, run it and the tests, and can explain every part of it.

## 9. Known limits / what I would do next
- The automated tests run on SQLite; the full pipeline is meant for MySQL, so run it once against MySQL (section 3) before relying on the numbers.
- Loading uses batched inserts. For a much larger dataset I would use `LOAD DATA INFILE` or per-month batches.
- I would add an incremental load (only new invoices) and a small pre-aggregated monthly table if the API got slow.
- I would add API pagination for large result sets and a foreign-key / data-quality check script after each load.
