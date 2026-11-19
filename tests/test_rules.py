"""Unit tests for the fiddly rules. R2 and R7 are the ones the brief warns about."""
from decimal import Decimal

import pandas as pd

from pipeline import rules


def _lines(rows):
    """Tiny helper: build the DataFrame the rules expect."""
    df = pd.DataFrame(rows, columns=["invoice_no", "quantity", "invoice_ts", "price"])
    df["stock_code"] = "X"
    df["source_sheet"] = "s"
    df["source_row"] = range(2, len(df) + 2)
    df["invoice_ts"] = pd.to_datetime(df["invoice_ts"])
    df["price_num"] = pd.to_numeric(df["price"])
    df["price_dec"] = df["price"].map(Decimal)
    return df


# ---------------------------------------------------------------- R2
def test_r2_cancellation_is_only_the_c_prefix_not_negative_quantity():
    df = _lines([
        ("C100", -2, "2011-01-03", "1.0"),   # cancellation
        ("101", -4, "2011-01-03", "1.0"),    # negative qty, normal invoice -> write-off
        ("102", 5, "2011-01-03", "1.0"),     # normal sale
        ("c103", -1, "2011-01-03", "1.0"),   # lower-case c still a cancellation
    ])
    out, issues = rules.r2_cancellations(df)
    assert out["is_cancellation"].tolist() == [True, False, False, True]
    assert out["is_stock_writeoff"].tolist() == [False, True, False, False]
    # counted separately
    assert out["is_cancellation"].sum() == 2
    assert out["is_stock_writeoff"].sum() == 1
    assert set(issues["issue_type"]) == {"cancellation", "stock_writeoff"}


def test_r2_a_c_invoice_with_positive_quantity_is_still_a_cancellation_not_a_writeoff():
    df = _lines([("C200", 3, "2011-01-03", "1.0")])
    out, _ = rules.r2_cancellations(df)
    assert out["is_cancellation"].iloc[0] and not out["is_stock_writeoff"].iloc[0]


# ---------------------------------------------------------------- R7
FX = pd.DataFrame({
    "rate_date": pd.to_datetime(["2011-03-03", "2011-03-04", "2011-03-07"]).astype("datetime64[ns]"),
    "rate": ["1.6000", "1.6100", "1.6300"],
})  # Fri 4 March, then Mon 7 March: the weekend 5-6 March has no rows


def test_r7_weekend_uses_most_recent_earlier_rate_and_loses_no_rows():
    df = rules.r6_line_total(_lines([
        ("1", 1, "2011-03-04 09:00", "10.00"),   # Friday   -> its own rate
        ("2", 1, "2011-03-05 09:00", "10.00"),   # Saturday -> Friday's rate
        ("3", 1, "2011-03-06 23:59", "10.00"),   # Sunday   -> Friday's rate
        ("4", 1, "2011-03-07 00:01", "10.00"),   # Monday   -> Monday's rate
    ]).assign(is_non_product=False, is_free_sample=False, is_stock_writeoff=False))
    out, issues = rules.r7_convert_to_usd(df, FX)
    assert len(out) == 4 and issues.empty                       # a plain join would lose weekends
    assert out["fx_rate"].tolist() == [Decimal("1.6100"), Decimal("1.6100"),
                                       Decimal("1.6100"), Decimal("1.6300")]
    assert [str(d) for d in out["fx_rate_date"]] == ["2011-03-04", "2011-03-04",
                                                     "2011-03-04", "2011-03-07"]
    assert out["gross_usd"].iloc[1] == Decimal("10.00") * Decimal("1.6100")


def test_r7_never_uses_a_later_rate():
    # 2011-03-02 is BEFORE the first rate in the table: there is no earlier rate,
    # so the row must be rejected and logged, NOT given the later 2011-03-03 rate.
    df = rules.r6_line_total(_lines([("1", 1, "2011-03-02 09:00", "10.00")])
                             .assign(is_non_product=False, is_free_sample=False, is_stock_writeoff=False))
    out, issues = rules.r7_convert_to_usd(df, FX)
    assert out.empty
    assert issues["issue_type"].tolist() == ["no_fx_rate"]


def test_r7_keeps_row_order_and_exact_decimal_maths():
    df = rules.r6_line_total(_lines([
        ("a", 3, "2011-03-07 10:00", "0.10"),
        ("b", 2, "2011-03-03 10:00", "0.10"),
    ]).assign(is_non_product=False, is_free_sample=False, is_stock_writeoff=False))
    out, _ = rules.r7_convert_to_usd(df, FX)
    assert out["invoice_no"].tolist() == ["a", "b"]                     # original order kept
    assert out["gross_gbp"].tolist() == [Decimal("0.30"), Decimal("0.20")]  # no float error
    assert out["gross_usd"].iloc[0] == Decimal("0.30") * Decimal("1.6300")


# ---------------------------------------------------------------- other rules
def test_r1_removes_exact_duplicates_only():
    raw = pd.DataFrame({c: ["a", "a", "a"] for c in rules.RAW_FIELDS})
    raw.loc[2, "quantity"] = "different"
    raw["source_sheet"] = "s"
    raw["source_row"] = [2, 3, 4]
    out, issues = rules.r1_remove_duplicates(raw)
    assert len(out) == 2 and len(issues) == 1 and issues["source_row"].iloc[0] == 3


def test_r4_matches_codes_ignoring_case():
    df = _lines([("1", 1, "2011-01-03", "1.0")]).assign(stock_code="m")
    np_codes = pd.DataFrame({"stock_code": ["M", "POST"], "reason": ["Manual", "Postage"]})
    out, _ = rules.r4_non_product(df, np_codes)
    assert out["is_non_product"].iloc[0]


def test_r5_zero_is_kept_negative_is_rejected():
    df = _lines([("1", 1, "2011-01-03", "0"), ("2", 1, "2011-01-03", "-5"), ("3", 1, "2011-01-03", "2")])
    out, issues = rules.r5_odd_prices(df)
    assert out["invoice_no"].tolist() == ["1", "3"]
    assert out["is_free_sample"].tolist() == [True, False]
    assert issues[issues["action"] == "rejected"]["invoice_no"].tolist() == ["2"]


def test_r8_unknown_countries_stay_unknown_and_rows_are_kept():
    df = _lines([("1", 1, "2011-01-03", "1.0")] * 2).assign(country_raw=["Unspecified", "Atlantis"])
    mapping = pd.DataFrame({"country_raw": ["Unspecified"], "country_name": ["Unknown"], "region": ["Unknown"]})
    out, issues, full = rules.r8_country_region(df, mapping)
    assert len(out) == 2
    assert set(full["country_raw"]) == {"Unspecified", "Atlantis"}
    assert (full["country_name"] == "Unknown").all()
