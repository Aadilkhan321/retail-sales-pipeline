"""The Kaggle download is one CSV; it must be split back into the two sheets."""
import pandas as pd

from pipeline import extract
from tests.make_sample_data import COLS, sheet_1, sheet_2


def test_csv_is_split_back_into_two_sheets(tmp_path):
    s1, s2 = sheet_1(), sheet_2()
    p = tmp_path / "online_retail_II.csv"
    pd.concat([s1, s2]).to_csv(p, index=False)
    sheets = extract.read_workbook(p)
    assert list(sheets) == ["Year 2009-2010", "Year 2010-2011"]
    assert [len(v) for v in sheets.values()] == [len(s1), len(s2)]
    assert list(sheets["Year 2009-2010"].columns) == COLS


def test_csv_text_cells_are_not_turned_into_missing(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
                 "1,A,NA,1,2010-01-01 10:00:00,1.5,,France\n")
    df = extract.read_workbook(p)["csv"]
    assert df["Description"].iloc[0] == "NA" and pd.isna(df["Customer ID"].iloc[0])
