# RESULTS

_Generated automatically by `python -m pipeline.run` on 2026-11-19. Money is summed in SQL and rounded to 2 decimals only at the end._

**Revenue definition (see ASSUMPTIONS.md, R2/R4/R5):** product lines only, free samples (price 0) and stock write-offs excluded, cancellation lines (invoice starts with C) **included as negatives**, so it is net of cancellations. The sales-only figure (cancellations left out) is shown as well.

## 1. Rows

| What | Number |
|---|---:|
| Rows read in total (both sheets) | 1,067,371 |
| &nbsp;&nbsp;of which sheet `Year 2010-2011` | 541,910 |
| &nbsp;&nbsp;of which sheet `Year 2009-2010` | 525,461 |
| R1 exact duplicates removed | 34,335 |
| Unreadable rows rejected (not an official rule) | 0 |
| Rejected by R5 (negative price) | 5 |
| Rows rejected by R7 (no earlier FX rate) | 0 |
| Rows loaded into `fact_invoice_line` | 1,033,031 |

## 2. R2 - cancellations vs negative quantities

| What | Number |
|---|---:|
| Cancellation lines (invoice starts with C) | 19,104 |
| Negative-quantity lines that are NOT cancellations (stock write-offs) | 3,393 |

## 3. R4 and R5 - rows excluded from revenue

| What | Number |
|---|---:|
| R4 non-product rows (kept, marked, no product revenue) | 5,674 |
| R5 zero-price rows (kept, no revenue) | 6,014 |
| R5 negative-price rows (rejected) | 5 |
| Overlap: R4 rows that also have price 0 | 27 |
| Overlap: R4 rows that also have a negative price | 0 |

## 4. Customers

Distinct customers (placeholder `GUEST` not counted): **5,942**

## 5. Revenue

| Period | GBP | USD |
|---|---:|---:|
| Whole period (net of cancellations) | 18,932,945.36 | 29,888,761.09 |
| Whole period (sales only, cancellations left out) | 19,657,410.92 | 31,029,432.22 |
| December 2010 (net of cancellations) | 758,167.09 | 1,188,446.56 |

## 6. Top 5 products by USD revenue, March 2011

| # | Stock code | Description | USD | GBP |
|---:|---|---|---:|---:|
| 1 | 22423 | REGENCY CAKESTAND 3 TIER | 27,178.96 | 16,817.85 |
| 2 | 85099B | JUMBO BAG RED RETROSPOT | 16,316.73 | 10,116.43 |
| 3 | 47566 | PARTY BUNTING | 14,675.35 | 9,098.27 |
| 4 | 85099F | JUMBO BAG STRAWBERRY | 9,431.88 | 5,853.80 |
| 5 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | 8,958.84 | 5,550.95 |

## 7. R7 check

Rows before FX step: 1,033,031; after: 1,033,031 (a plain join would have lost the weekend rows). Lines that used an earlier day's rate (weekends/holidays): 133,419.

## 8. Data-quality issues per rule

| Rule | Issues logged |
|---|---:|
| R1 | 34,335 |
| R2 | 22,497 |
| R3 | 235,151 |
| R4 | 5,674 |
| R5 | 6,019 |
| R8 | 813 |
| **Total** | **304,489** |

Breakdown:

| Rule | Type | Action | Count |
|---|---|---|---:|
| R1 | exact_duplicate | removed | 34,335 |
| R2 | cancellation | flagged | 19,104 |
| R2 | stock_writeoff | flagged | 3,393 |
| R3 | missing_customer_id | corrected | 235,151 |
| R4 | non_product_code | flagged | 5,674 |
| R5 | negative_price | rejected | 5 |
| R5 | zero_price_free_sample | flagged | 6,014 |
| R8 | country_unknown | flagged | 813 |
