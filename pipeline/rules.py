"""Part 2: the eight cleaning rules, one small function per rule.

Every function takes a DataFrame and returns (new_dataframe, issues_dataframe).
`issues` is the audit log: nothing is dropped or changed without a row in it.
Rules are applied in the order R1 -> R8 by `clean()` at the bottom of the file.
"""
from decimal import Decimal

import pandas as pd

from .config import PLACEHOLDER_CUSTOMER

ISSUE_COLS = ["rule", "issue_type", "action", "source_sheet", "source_row",
              "invoice_no", "stock_code", "detail"]

# The 8 columns of the original workbook (after renaming). Used for R1.
RAW_FIELDS = ["invoice_no", "stock_code", "description", "quantity", "invoice_ts",
              "price", "customer_id", "country_raw"]


def _issues(df: pd.DataFrame, rule: str, issue_type: str, action: str, detail) -> pd.DataFrame:
    out = df[["source_sheet", "source_row", "invoice_no", "stock_code"]].copy()
    out["rule"] = rule
    out["issue_type"] = issue_type
    out["action"] = action
    out["detail"] = detail
    return out[ISSUE_COLS]


# --------------------------------------------------------------------------- R1
def r1_remove_duplicates(df: pd.DataFrame):
    """R1: rows identical in all 8 original columns (timestamp included).
    The first one is kept (2009-2010 sheet first, then top-to-bottom)."""
    dup = df.duplicated(subset=RAW_FIELDS, keep="first")
    issues = _issues(df[dup], "R1", "exact_duplicate", "removed",
                     "Identical to an earlier row in all 8 columns")
    return df[~dup].copy(), issues


# ------------------------------------------------------------------- (parsing)
def parse_types(df: pd.DataFrame):
    """Turn text into proper types. Rows that cannot be read are rejected and logged
    (rule 'PARSE'). Expected to be zero on the real file."""
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    price = pd.to_numeric(df["price"], errors="coerce")
    ts = pd.to_datetime(df["invoice_ts"], errors="coerce")
    bad = qty.isna() | price.isna() | ts.isna() | df["invoice_no"].isna() | df["stock_code"].isna()
    issues = _issues(df[bad], "PARSE", "unreadable_value", "rejected",
                     "Invoice, StockCode, Quantity, Price or InvoiceDate could not be read")
    ok = df[~bad].copy()
    ok["invoice_no"] = ok["invoice_no"].str.strip()
    ok["quantity"] = qty[~bad].astype("int64")
    ok["price_num"] = price[~bad]
    ok["price_dec"] = ok["price"].map(Decimal)  # exact decimal from the original text
    ok["invoice_ts"] = ts[~bad]
    return ok, issues


# --------------------------------------------------------------------------- R2
def r2_cancellations(df: pd.DataFrame):
    """R2: a cancellation is ONLY an invoice number starting with 'C'.
    A negative quantity on a normal invoice is a stock write-off, a different thing.
    Both are flagged and kept; they are counted separately."""
    out = df.copy()
    out["is_cancellation"] = out["invoice_no"].str.upper().str.startswith("C")
    out["is_stock_writeoff"] = (out["quantity"] < 0) & ~out["is_cancellation"]
    issues = pd.concat([
        _issues(out[out["is_cancellation"]], "R2", "cancellation", "flagged",
                "Invoice number starts with C"),
        _issues(out[out["is_stock_writeoff"]], "R2", "stock_writeoff", "flagged",
                "Negative quantity on a normal (non-C) invoice"),
    ])
    return out, issues


# --------------------------------------------------------------------------- R3
def r3_missing_customer(df: pd.DataFrame):
    """R3: blank Customer ID -> single placeholder customer. Rows are kept."""
    out = df.copy()
    cid = out["customer_id"].fillna("").str.strip().str.replace(r"\.0+$", "", regex=True)
    blank = cid == ""
    out["customer_id"] = cid.mask(blank, PLACEHOLDER_CUSTOMER)
    out["is_guest"] = blank
    issues = _issues(out[blank], "R3", "missing_customer_id", "corrected",
                     f"Blank Customer ID, grouped under placeholder '{PLACEHOLDER_CUSTOMER}'")
    return out, issues


# --------------------------------------------------------------------------- R4
def r4_non_product(df: pd.DataFrame, non_product: pd.DataFrame):
    """R4: stock codes that are postage / fees / adjustments. Matching ignores case.
    Rows are kept and marked, and are left out of product revenue."""
    out = df.copy()
    out["stock_code"] = out["stock_code"].str.strip().str.upper()
    reasons = {c.strip().upper(): r for c, r in zip(non_product["stock_code"], non_product["reason"])}
    out["is_non_product"] = out["stock_code"].isin(reasons)
    detail = out["stock_code"].map(reasons)
    issues = _issues(out[out["is_non_product"]], "R4", "non_product_code", "flagged",
                     detail[out["is_non_product"]])
    return out, issues


# --------------------------------------------------------------------------- R5
def r5_odd_prices(df: pd.DataFrame):
    """R5: price = 0 -> free sample (kept, no revenue). Price < 0 -> mistake, rejected."""
    neg = df["price_num"] < 0
    zero = df["price_num"] == 0
    issues = pd.concat([
        _issues(df[zero], "R5", "zero_price_free_sample", "flagged",
                "Price is 0: kept but not counted as revenue"),
        _issues(df[neg], "R5", "negative_price", "rejected",
                "Price below 0: treated as a mistake and rejected"),
    ])
    out = df[~neg].copy()
    out["is_free_sample"] = zero[~neg]
    return out, issues


# --------------------------------------------------------------------------- R6
def r6_line_total(df: pd.DataFrame):
    """R6: gross_gbp = Quantity x Price, as exact Decimal. NOT rounded here;
    rounding to 2 places happens only on the final sums."""
    out = df.copy()
    out["gross_gbp"] = [Decimal(int(q)) * p for q, p in zip(out["quantity"], out["price_dec"])]
    # Revenue = a real product line, with a real price, that is not a stock write-off.
    out["is_revenue"] = ~out["is_non_product"] & ~out["is_free_sample"] & ~out["is_stock_writeoff"]
    return out


# --------------------------------------------------------------------------- R7
def load_fx(path) -> pd.DataFrame:
    fx = pd.read_csv(path, dtype=str)
    fx = fx[(fx["from_currency"] == "GBP") & (fx["to_currency"] == "USD")].copy()
    fx["rate_date"] = pd.to_datetime(fx["rate_date"]).astype("datetime64[ns]")
    fx = fx.drop_duplicates("rate_date", keep="last").sort_values("rate_date")
    return fx[["rate_date", "rate"]].reset_index(drop=True)


def r7_convert_to_usd(df: pd.DataFrame, fx: pd.DataFrame):
    """R7: use the rate for the invoice date; if that date has no rate (weekend, holiday)
    use the most recent EARLIER rate (merge_asof, direction='backward'). Never a later one.
    A plain join would lose every weekend row, so the row count is checked."""
    before = len(df)
    left = df.copy()
    left["_pos"] = range(before)
    left["_day"] = left["invoice_ts"].dt.normalize().astype("datetime64[ns]")
    left = left.sort_values("_day", kind="stable")
    right = fx.rename(columns={"rate_date": "fx_rate_date", "rate": "_rate_text"})
    right = right.assign(fx_rate_date=right["fx_rate_date"].astype("datetime64[ns]"))
    merged = pd.merge_asof(left, right, left_on="_day", right_on="fx_rate_date",
                           direction="backward")
    if len(merged) != before:  # safety net: the join must never change the row count
        raise RuntimeError(f"R7 changed the row count: {before} -> {len(merged)}")
    merged = merged.sort_values("_pos")
    missing = merged["fx_rate_date"].isna()
    issues = _issues(merged[missing], "R7", "no_fx_rate", "rejected",
                     "No FX rate on or before the invoice date")
    ok = merged[~missing].copy()
    ok["fx_rate"] = ok["_rate_text"].map(Decimal)
    ok["gross_usd"] = [g * r for g, r in zip(ok["gross_gbp"], ok["fx_rate"])]
    ok["fx_rate_date"] = ok["fx_rate_date"].dt.date
    # Safety net: a rate may never come from AFTER the invoice day.
    assert (pd.to_datetime(ok["fx_rate_date"]) <= ok["_day"]).all()
    return ok.drop(columns=["_pos", "_day", "_rate_text"]), issues


# --------------------------------------------------------------------------- R8
def r8_country_region(df: pd.DataFrame, mapping: pd.DataFrame):
    """R8: map Country -> tidy name + region. 'European Community' and 'Unspecified' stay
    'Unknown' (kept, not guessed). A country missing from the mapping file would also
    become Unknown (and be logged), so no row is ever lost."""
    out = df.copy()
    out["country_raw"] = out["country_raw"].fillna("(blank)").str.strip()
    known = set(mapping["country_raw"])
    extra = sorted(set(out["country_raw"]) - known)
    full = mapping.copy()
    if extra:
        full = pd.concat([full, pd.DataFrame({"country_raw": extra,
                                              "country_name": "Unknown",
                                              "region": "Unknown"})], ignore_index=True)
    unknown_raw = set(full.loc[full["country_name"] == "Unknown", "country_raw"])
    is_unknown = out["country_raw"].isin(unknown_raw)
    is_unmapped = out["country_raw"].isin(extra)
    issues = pd.concat([
        _issues(out[is_unknown & ~is_unmapped], "R8", "country_unknown", "flagged",
                "Country maps to Unknown; kept as Unknown"),
        _issues(out[is_unmapped], "R8", "country_not_in_mapping", "flagged",
                "Country not in country_region.csv; set to Unknown"),
    ])
    return out, issues, full


# ------------------------------------------------------------------ orchestrator
def clean(raw: pd.DataFrame, non_product: pd.DataFrame, fx: pd.DataFrame,
          country_map: pd.DataFrame):
    """Run R1..R8 in order. Returns (clean_df, issues_df, country_map, stats)."""
    stats: dict = {"rows_read": int(len(raw))}
    stats["rows_read_by_sheet"] = {k: int(v) for k, v in raw["source_sheet"].value_counts().items()}
    issues = []

    df, i = r1_remove_duplicates(raw); issues.append(i)
    stats["r1_duplicates_removed"] = int(len(i))

    df, i = parse_types(df); issues.append(i)
    stats["unreadable_rows_rejected"] = int(len(i))

    df, i = r2_cancellations(df); issues.append(i)
    stats["r2_cancellation_lines"] = int(df["is_cancellation"].sum())
    stats["r2_negative_qty_not_cancellation"] = int(df["is_stock_writeoff"].sum())

    df, i = r3_missing_customer(df); issues.append(i)
    stats["r3_rows_without_customer_id"] = int(df["is_guest"].sum())

    df, i = r4_non_product(df, non_product); issues.append(i)
    stats["r4_non_product_rows"] = int(df["is_non_product"].sum())

    stats["r4_and_negative_price_overlap"] = int((df["is_non_product"] & (df["price_num"] < 0)).sum())
    df, i = r5_odd_prices(df); issues.append(i)
    stats["r5_zero_price_rows"] = int(df["is_free_sample"].sum())
    stats["r5_negative_price_rejected"] = int((i["issue_type"] == "negative_price").sum())
    stats["r4_and_zero_price_overlap"] = int((df["is_non_product"] & df["is_free_sample"]).sum())

    df = r6_line_total(df)

    n_before = len(df)
    df, i = r7_convert_to_usd(df, fx); issues.append(i)
    stats["r7_rows_before"] = int(n_before)
    stats["r7_rows_after"] = int(len(df))
    stats["r7_rows_using_earlier_rate"] = int((pd.to_datetime(df["fx_rate_date"]) != df["invoice_ts"].dt.normalize()).sum())

    df, i, country_map = r8_country_region(df, country_map); issues.append(i)

    stats["rows_loaded"] = int(len(df))
    return df.reset_index(drop=True), pd.concat(issues, ignore_index=True), country_map, stats
