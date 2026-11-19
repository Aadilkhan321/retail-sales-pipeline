"""Part 3: build the dimensions + fact table from the clean data and load them into MySQL."""
import pandas as pd
from sqlalchemy import insert

from . import db
from .config import PLACEHOLDER_CUSTOMER

CHUNK = 5000


def _records(df: pd.DataFrame):
    """DataFrame -> list of plain-Python dicts (NaN/NaT -> None)."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def _insert(conn, table, df: pd.DataFrame) -> None:
    rows = _records(df[[c.name for c in table.columns]])
    for i in range(0, len(rows), CHUNK):
        conn.execute(insert(table), rows[i:i + CHUNK])


def build_tables(df: pd.DataFrame, country_map: pd.DataFrame, issues: pd.DataFrame) -> dict:
    # ---- dim_country: one row per raw country value (43 + anything unmapped)
    dim_country = country_map.reset_index(drop=True).copy()
    dim_country["country_key"] = range(1, len(dim_country) + 1)
    country_key = dict(zip(dim_country["country_raw"], dim_country["country_key"]))

    # ---- dim_date: every calendar day from first to last invoice
    days = pd.date_range(df["invoice_ts"].min().normalize(), df["invoice_ts"].max().normalize())
    dim_date = pd.DataFrame({"full_date": days.date})
    dim_date["date_key"] = days.strftime("%Y%m%d").astype(int)
    dim_date["cal_year"] = days.year
    dim_date["cal_month"] = days.month
    dim_date["month_key"] = days.strftime("%Y-%m")
    dim_date["day_of_week"] = days.day_of_week
    dim_date["is_weekend"] = days.day_of_week >= 5

    # ---- dim_product: one row per (upper-case) stock code; description = most common one
    desc = (df.dropna(subset=["description"])
              .assign(description=lambda d: d["description"].str.strip())
              .groupby(["stock_code", "description"]).size().reset_index(name="n")
              .sort_values(["stock_code", "n", "description"], ascending=[True, False, True])
              .drop_duplicates("stock_code")[["stock_code", "description"]])
    dim_product = (df.groupby("stock_code", as_index=False)["is_non_product"].max()
                     .merge(desc, on="stock_code", how="left"))
    dim_product["description"] = dim_product["description"].str.slice(0, 255)
    dim_product.insert(0, "product_key", range(1, len(dim_product) + 1))
    product_key = dict(zip(dim_product["stock_code"], dim_product["product_key"]))

    # ---- dim_customer: GUEST placeholder + one row per real customer.
    #      The customer's country = the country on their most recent line.
    latest = (df.sort_values(["invoice_ts", "source_sheet", "source_row"])
                .groupby("customer_id", as_index=False).last()[["customer_id", "country_raw"]])
    dim_customer = latest.sort_values("customer_id").reset_index(drop=True)
    dim_customer["customer_key"] = range(1, len(dim_customer) + 1)
    dim_customer["is_placeholder"] = dim_customer["customer_id"] == PLACEHOLDER_CUSTOMER
    dim_customer["country_key"] = dim_customer["country_raw"].map(country_key)
    customer_key = dict(zip(dim_customer["customer_id"], dim_customer["customer_key"]))

    # ---- fact table
    fact = pd.DataFrame({
        "line_id": range(1, len(df) + 1),
        "invoice_no": df["invoice_no"],
        "invoice_ts": pd.Series(df["invoice_ts"].dt.to_pydatetime(), index=df.index, dtype=object),
        "date_key": df["invoice_ts"].dt.strftime("%Y%m%d").astype(int),
        "customer_key": df["customer_id"].map(customer_key),
        "product_key": df["stock_code"].map(product_key),
        "country_key": df["country_raw"].map(country_key),
        "quantity": df["quantity"],
        "unit_price_gbp": df["price_dec"],
        "gross_gbp": df["gross_gbp"],
        "fx_rate": df["fx_rate"],
        "fx_rate_date": df["fx_rate_date"],
        "gross_usd": df["gross_usd"],
        "is_cancellation": df["is_cancellation"],
        "is_stock_writeoff": df["is_stock_writeoff"],
        "is_non_product": df["is_non_product"],
        "is_free_sample": df["is_free_sample"],
        "is_revenue": df["is_revenue"],
        "source_sheet": df["source_sheet"],
        "source_row": df["source_row"],
    })
    assert fact[["customer_key", "product_key", "country_key"]].notna().all().all()

    dq = issues.reset_index(drop=True).copy()
    dq.insert(0, "issue_id", range(1, len(dq) + 1))
    dq["detail"] = dq["detail"].astype("object").map(lambda v: v if v is None or pd.isna(v) else str(v)[:255])

    return {"dim_date": dim_date, "dim_country": dim_country, "dim_customer": dim_customer,
            "dim_product": dim_product, "fact_invoice_line": fact, "data_quality_issue": dq}


def load_all(engine, tables: dict) -> None:
    """Empty the schema and load everything in one transaction.
    Because the tables are dropped and re-created first, running twice never doubles rows."""
    db.reset_schema(engine)
    order = ["dim_date", "dim_country", "dim_customer", "dim_product",
             "fact_invoice_line", "data_quality_issue"]
    with engine.begin() as conn:
        for name in order:
            _insert(conn, db.metadata.tables[name], tables[name])
