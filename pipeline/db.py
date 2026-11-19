"""Database tables (star schema) and engine helpers.

The tables are defined once with SQLAlchemy, and `python -m pipeline.make_schema`
turns them into the plain MySQL CREATE TABLE statements in sql/schema.sql.

Money is DECIMAL everywhere. Line values are stored with extra decimal places
(un-rounded) because the brief says to round only at the very end; the API and
RESULTS.md round the final SUMs to 2 places.
"""
from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    MetaData, Numeric, String, Table, create_engine,
)
from sqlalchemy.engine import URL, make_url

import os

from . import config

metadata = MetaData()
_MYSQL = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

dim_date = Table(
    "dim_date", metadata,
    Column("date_key", Integer, primary_key=True, autoincrement=False),  # 20101231
    Column("full_date", Date, nullable=False, unique=True),
    Column("cal_year", Integer, nullable=False),
    Column("cal_month", Integer, nullable=False),
    Column("month_key", String(7), nullable=False),  # '2010-12'
    Column("day_of_week", Integer, nullable=False),  # 0 = Monday
    Column("is_weekend", Boolean, nullable=False),
    Index("ix_dim_date_month_key", "month_key"),
    **_MYSQL,
)

dim_country = Table(
    "dim_country", metadata,
    Column("country_key", Integer, primary_key=True, autoincrement=False),
    Column("country_raw", String(60), nullable=False, unique=True),
    Column("country_name", String(60), nullable=False),
    Column("region", String(60), nullable=False),
    Index("ix_dim_country_region", "region"),
    **_MYSQL,
)

dim_customer = Table(
    "dim_customer", metadata,
    Column("customer_key", Integer, primary_key=True, autoincrement=False),
    Column("customer_id", String(20), nullable=False, unique=True),
    Column("is_placeholder", Boolean, nullable=False),  # True only for GUEST (R3)
    Column("country_key", Integer, ForeignKey("dim_country.country_key"), nullable=False),
    **_MYSQL,
)

dim_product = Table(
    "dim_product", metadata,
    Column("product_key", Integer, primary_key=True, autoincrement=False),
    Column("stock_code", String(40), nullable=False, unique=True),
    Column("description", String(255)),
    Column("is_non_product", Boolean, nullable=False),  # R4
    **_MYSQL,
)

fact_invoice_line = Table(
    "fact_invoice_line", metadata,
    Column("line_id", BigInteger, primary_key=True, autoincrement=False),
    Column("invoice_no", String(20), nullable=False),
    Column("invoice_ts", DateTime, nullable=False),
    Column("date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column("customer_key", Integer, ForeignKey("dim_customer.customer_key"), nullable=False),
    Column("product_key", Integer, ForeignKey("dim_product.product_key"), nullable=False),
    Column("country_key", Integer, ForeignKey("dim_country.country_key"), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price_gbp", Numeric(14, 6), nullable=False),
    Column("gross_gbp", Numeric(20, 6), nullable=False),   # R6 quantity x price
    Column("fx_rate", Numeric(10, 6), nullable=False),     # R7 rate used
    Column("fx_rate_date", Date, nullable=False),          # R7 date the rate came from
    Column("gross_usd", Numeric(24, 10), nullable=False),  # R7 gross_gbp x fx_rate
    Column("is_cancellation", Boolean, nullable=False),    # R2: invoice starts with C
    Column("is_stock_writeoff", Boolean, nullable=False),  # R2: negative qty, normal invoice
    Column("is_non_product", Boolean, nullable=False),     # R4
    Column("is_free_sample", Boolean, nullable=False),     # R5: price = 0
    Column("is_revenue", Boolean, nullable=False),         # counts towards revenue
    Column("source_sheet", String(40), nullable=False),
    Column("source_row", Integer, nullable=False),         # Excel row number
    Index("ix_fact_date", "date_key"),
    Index("ix_fact_customer", "customer_key"),
    Index("ix_fact_product_date", "product_key", "date_key"),
    Index("ix_fact_country", "country_key"),
    Index("ix_fact_invoice", "invoice_no"),
    Index("ux_fact_source", "source_sheet", "source_row", unique=True),
    **_MYSQL,
)

data_quality_issue = Table(
    "data_quality_issue", metadata,
    Column("issue_id", BigInteger, primary_key=True, autoincrement=False),
    Column("rule", String(8), nullable=False),         # R1 ... R8
    Column("issue_type", String(40), nullable=False),  # e.g. cancellation, negative_price
    Column("action", String(12), nullable=False),      # removed / rejected / flagged / corrected
    Column("source_sheet", String(40)),
    Column("source_row", Integer),
    Column("invoice_no", String(20)),
    Column("stock_code", String(40)),
    Column("detail", String(255)),
    Index("ix_dqi_rule", "rule"),
    **_MYSQL,
)


def _url(url: str | None = None) -> str:
    """Explicit URL > DATABASE_URL environment variable > default from config.py."""
    return url or os.getenv("DATABASE_URL") or config.DATABASE_URL


def get_engine(url: str | None = None):
    return create_engine(_url(url), pool_pre_ping=True, future=True)


def ensure_database(url: str | None = None) -> None:
    """MySQL only: create the database if it does not exist yet."""
    u = make_url(_url(url))
    if not u.drivername.startswith("mysql") or not u.database:
        return
    # NB: URL.set(database=None) would NOT remove the database name, so build a URL without one.
    server_url = URL.create(u.drivername, username=u.username, password=u.password,
                            host=u.host, port=u.port, query=u.query)
    server = create_engine(server_url, future=True)
    with server.begin() as conn:
        conn.exec_driver_sql(
            f"CREATE DATABASE IF NOT EXISTS `{u.database}` CHARACTER SET utf8mb4"
        )
    server.dispose()


def reset_schema(engine) -> None:
    """Drop and re-create every table. This is what makes re-runs idempotent."""
    metadata.drop_all(engine)
    metadata.create_all(engine)
