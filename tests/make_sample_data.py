"""Builds a SMALL fake workbook with the same shape as the real Online Retail II file
and with every messy case from the assessment in it (duplicates, C-invoices, negative
quantities, blank customers, POST/m codes, zero and negative prices, weekend dates, ...).

Used by the tests and for a quick demo run:

    python tests/make_sample_data.py data/sample/sample_retail.xlsx
    python -m pipeline.run --excel data/sample/sample_retail.xlsx
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

COLS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
NA = None
D = datetime


def sheet_1():
    rows = [
        # 0  normal sale
        [489434, "85048", "DESC A", 12, D(2009, 12, 1, 7, 45), 6.95, 13085.0, "United Kingdom"],
        # 1  exact duplicate of row 0 (R1)
        [489434, "85048", "DESC A", 12, D(2009, 12, 1, 7, 45), 6.95, 13085.0, "United Kingdom"],
        # 2  normal sale
        [489435, "22350", "CAT BOWL", 12, D(2009, 12, 1, 7, 46), 2.10, 13085.0, "United Kingdom"],
        # 3  cancellation (C invoice, negative qty)  (R2)
        ["C489449", "22350", "CAT BOWL", -12, D(2009, 12, 1, 9, 0), 2.10, 13085.0, "United Kingdom"],
        # 4  negative qty on a normal invoice, price 0: stock write-off + free sample (R2/R5)
        [489436, "21232", "damaged", -5, D(2009, 12, 1, 10, 0), 0.0, NA, "United Kingdom"],
        # 5  negative qty on a normal invoice, real price, no customer (R2 write-off, R3)
        [489437, "22111", "SCOTTIE DOG", -3, D(2009, 12, 1, 10, 5), 4.00, NA, "United Kingdom"],
        # 6  postage (R4)
        [489438, "POST", "POSTAGE", 1, D(2009, 12, 1, 11, 0), 18.0, 12345.0, "France"],
        # 7  manual adjustment, lower-case code, no customer (R3, R4 case-insensitive)
        [489439, "m", "Manual", 1, D(2009, 12, 1, 11, 5), 5.0, NA, "United Kingdom"],
        # 8  negative price (R5 reject)
        [489440, "B", "Adjust bad debt", 1, D(2009, 12, 1, 12, 0), -11062.06, NA, "United Kingdom"],
        # 9  free sample, country maps to Unknown (R5, R8)
        [489441, "22960", "JAM MAKING SET", 1, D(2009, 12, 1, 12, 30), 0.0, 14000.0, "Unspecified"],
        # 10 Saturday sale -> must use FRIDAY's rate 2009-12-04 (R7)
        [489442, "85048", "DESC A", 2, D(2009, 12, 5, 10, 0), 6.95, 13085.0, "United Kingdom"],
    ]
    return pd.DataFrame(rows, columns=COLS)


def sheet_2():
    rows = [
        # the same line as sheet 1 row 2: the two sheets overlap -> duplicate across sheets (R1)
        [489435, "22350", "CAT BOWL", 12, D(2009, 12, 1, 7, 46), 2.10, 13085.0, "United Kingdom"],
        # December 2010
        [500001, "85123A", "WHITE HANGING HEART", 10, D(2010, 12, 3, 10, 0), 2.55, 15000.0, "United Kingdom"],
        [500002, "85123a", "WHITE HANGING HEART", 5, D(2010, 12, 4, 11, 0), 2.55, 15000.0, "United Kingdom"],  # Saturday
        [500003, "22960", "JAM MAKING SET", 3, D(2010, 12, 5, 12, 0), 3.00, 16000.0, "Germany"],               # Sunday
        # March 2011
        [510001, "84879", "ASSORTED COLOUR BIRD", 100, D(2011, 3, 10, 9, 0), 1.69, 17000.0, "European Community"],
        [510002, "22960", "JAM MAKING SET", 20, D(2011, 3, 11, 9, 0), 3.00, 16000.0, "Germany"],
        ["C510003", "84879", "ASSORTED COLOUR BIRD", -10, D(2011, 3, 12, 9, 0), 1.69, 17000.0, "European Community"],  # Saturday cancel
        [510004, "DOT", "DOTCOM POSTAGE", 1, D(2011, 3, 12, 9, 5), 40.0, NA, "United Kingdom"],
        [510005, "TEST001", "test", 1, D(2011, 3, 14, 9, 5), 1.0, NA, "United Kingdom"],
    ]
    return pd.DataFrame(rows, columns=COLS)


def build(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        sheet_1().to_excel(xw, sheet_name="Year 2009-2010", index=False)
        sheet_2().to_excel(xw, sheet_name="Year 2010-2011", index=False)
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample/sample_retail.xlsx")
    print("wrote", build(out))
