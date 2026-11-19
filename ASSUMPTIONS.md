# ASSUMPTIONS

Decisions I made where the brief left a choice, listed by rule number. Nothing is dropped
silently: every removed, rejected, corrected or flagged row is written to the table
`data_quality_issue` (rule, issue type, action, sheet, Excel row number, invoice, stock code, reason).

Rules are applied in the order R1 → R8. Rows are identified by `source_sheet` + `source_row`
(the Excel row number), so any logged issue can be traced back to the original workbook and to
the raw CSVs in `data/raw/`.

## General

- **Both sheets are one history.** They are read as text (so nothing is changed by pandas), stacked, and processed together.
- **Input file format (a mismatch with the brief).** The brief describes an Excel workbook with two sheets, but the Kaggle download is a single `online_retail_II.csv` with both sheets stacked (same 8 columns, same total row count). The pipeline accepts either. For the CSV it splits the file back into the two sheets at the one place where the dates jump backwards by more than a day (end of sheet 1 ≈ 9 Dec 2010, start of sheet 2 = 1 Dec 2010), and names the parts `Year 2009-2010` / `Year 2010-2011`. In that case `source_row` is the row number inside its part.
- **Revenue definition** (used for every "revenue" number, in RESULTS.md and in the API):
  a line counts as revenue when it is a real product (not R4), has a price above 0 (not R5 free sample)
  and is not a stock write-off (R2). **Cancellation lines (invoice starts with C) are included as
  negative amounts**, so revenue is *net of cancellations*. RESULTS.md also shows the "sales only"
  total (cancellations left out) so a reader can compare with either definition.
- **Units sold / invoice counts** (API) only count non-cancelled lines. Cancelled units are not counted
  as "sold", and a C invoice is not counted as an invoice. Revenue is still net.
- **Customer country.** Some customers appear under more than one country. `dim_customer.country_key`
  is the country on the customer's most recent line.
- **Product identity.** Stock codes are trimmed and upper-cased before loading, so `85123a` and `85123A`
  are the same product. The description stored is the most common (trimmed) description of that code, ties broken alphabetically.
- **Unreadable rows.** If a Quantity, Price or InvoiceDate cannot be read, the row is rejected and logged under the rule name `PARSE`. This is not one of the eight rules and is expected to be 0.
- **Re-runs.** Each run drops and re-creates all tables and loads again inside one transaction, so counts are identical on every run.
- **Rounding.** Money is exact `Decimal` in Python and `DECIMAL` in MySQL. Line values are stored un-rounded (6 / 10 decimal places). Rounding to 2 places is done only on the final sums (`ROUND(SUM(...), 2)` in SQL).
- **`/health`** returns HTTP 200 `{"status":"ok","database":"up"}`, or HTTP 503 with `"database":"down"` when MySQL cannot be reached.

## R1 – Exact duplicates
- "Exact" = all 8 original columns identical as text, timestamp included. No trimming or case-folding is done before comparing.
- The first occurrence is kept (2009-2010 sheet before 2010-2011 sheet, top to bottom). Every removed copy is logged.
- The two sheets overlap in time (both contain the first days of December 2010), so R1 also removes copies that sit in *different* sheets.

## R2 – Cancellations
- A cancellation is **only** an invoice number starting with `C` (case-insensitive, after trimming). Quantity is not used to decide this.
- A negative quantity on a normal invoice is a **stock write-off** (`is_stock_writeoff`). The two groups are flagged separately, counted separately, and both are kept.
- A `C` invoice with a positive quantity (if any exist) is still a cancellation, never a write-off.
- Write-offs are not customer sales, so they are left out of revenue.

## R3 – Blank Customer ID
- Blank IDs become one placeholder customer, `GUEST` (`dim_customer.is_placeholder = 1`). Rows are kept.
- Real IDs are cleaned of the Excel `.0` suffix (`13085.0` → `13085`).
- `GUEST` is excluded from: the distinct-customer count, and the customer endpoint (`/customers/GUEST/summary` returns 404). It *is* included in revenue, product and monthly KPI totals because those are real sales.
- Each blank-ID row is logged (action `corrected`).

## R4 – Non-product codes
- Codes in `non_product_codes.csv` are matched after trimming and upper-casing both sides, so `m` and `M` match (the file lists both; they are the same code once case is ignored).
- Rows are kept, marked `is_non_product`, and are not revenue.
- R4 is applied *before* R5, so a row can be counted under both (e.g. a non-product code with price 0). RESULTS.md reports the R4 total, the R5 totals and the overlaps separately.

## R5 – Odd prices
- Price = 0 → free sample: kept, `is_free_sample = 1`, not revenue (its gross value is 0 anyway).
- Price < 0 → mistake: **rejected**, not loaded into the fact table, logged with its original sheet and row number.

## R6 – Line total
- `gross_gbp = Quantity × Price`, calculated with Python `Decimal` from the original text of Price (no float is ever used). Cancellations and write-offs therefore have a negative gross.

## R7 – USD conversion
- The rate is chosen by the **date** part of the invoice timestamp.
- If that date has a rate, that rate is used. If not (weekend / holiday), the most recent rate *before* it is used (`merge_asof`, direction `backward`). A later rate is never used; a check in the code asserts this.
- If no rate exists on or before the date, the row would be rejected and logged (`no_fx_rate`). The FX file starts on 2009-10-30, before the first invoice, so this is expected to be 0.
- `fx_rate` and `fx_rate_date` are stored on every fact row. `gross_usd = gross_gbp × fx_rate`.
- The row count is compared before and after the join; the pipeline stops with an error if it changed.

## R8 – Country and region
- Country is mapped through `country_region.csv`. `European Community` and `Unspecified` stay `Unknown` / `Unknown`: kept, logged (action `flagged`), not guessed.
- If a country is ever missing from the mapping file it is also set to `Unknown` and logged as `country_not_in_mapping`, so no row can be lost.
- `dim_country` has one row per raw country value, so both Unknown values stay visible.

## Things in the brief that looked odd, and what I decided
1. **R5 vs R4.** R5 says zero-price lines are "free samples", but `non_product_codes.csv` also lists stock code `S` ("Samples"). A row can fall under both rules. Both flags are set; neither rule hides the row from the other, and the overlap is reported in RESULTS.md.
2. **`M` and `m` both listed** although R4 says to ignore case. Harmless; the codes are de-duplicated after upper-casing.
3. **"Treat both sheets as one history" but the sheets overlap.** The same December 2010 invoices appear in both. R1 handles it; this is why the R1 count includes cross-sheet copies.
4. **"Rate for that invoice date … otherwise the most recent rate before it".** I read this as: same-day rate if it exists, otherwise the latest earlier one. (The strict "before" reading would use the previous day even on weekdays, which contradicts "the rate for that invoice date".)
5. **Net vs gross revenue.** The brief does not say whether cancellations should reduce revenue. I used net (see General), and also report sales-only.
6. **R3 vs totals.** GUEST rows are excluded "from anything counted per customer" but are real sales, so they stay in totals.
7. **Number of data-quality issues.** Because corrected and flagged rows are logged too (not only rejected ones), R3 and R2 produce a large number of rows in `data_quality_issue`. Use the `action` column to separate `removed`/`rejected` from `flagged`/`corrected`.
