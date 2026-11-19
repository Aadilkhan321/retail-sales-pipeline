"""Part 1: read the workbook and keep an untouched copy (the audit trail)."""
import re
from pathlib import Path

import pandas as pd

RAW_COLUMNS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate",
               "Price", "Customer ID", "Country"]

# Internal (snake_case) names used from here on.
RENAME = {"Invoice": "invoice_no", "StockCode": "stock_code", "Description": "description",
          "Quantity": "quantity", "InvoiceDate": "invoice_ts", "Price": "price",
          "Customer ID": "customer_id", "Country": "country_raw"}


def _check_columns(name: str, df: pd.DataFrame) -> pd.DataFrame:
    missing = set(RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"'{name}' is missing columns: {sorted(missing)}")
    return df[RAW_COLUMNS]


def read_csv_as_sheets(path: Path) -> dict[str, pd.DataFrame]:
    """The Kaggle download is ONE csv with both sheets stacked (sheet 1 rows, then sheet 2 rows).
    Read it as text, then split it back into the two sheets at the point where the dates jump
    backwards (sheet 1 ends around 2010-12-09, sheet 2 starts again on 2010-12-01).
    If no such jump exists the file is kept as a single part."""
    df = None
    for enc in ("utf-8", "latin-1"):
        try:
            # keep_default_na=False: only a truly empty cell is "missing" (not text like "NA")
            df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise ValueError(f"Could not read {path} as UTF-8 or Latin-1")
    df = _check_columns(path.name, df)
    ts = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    jump = (ts - ts.shift(1)).dt.total_seconds()
    if jump.notna().any() and jump.min() <= -86400:        # a drop of a day or more
        cut = int(jump.idxmin())
        return {"Year 2009-2010": df.iloc[:cut].reset_index(drop=True),
                "Year 2010-2011": df.iloc[cut:].reset_index(drop=True)}
    return {"csv": df}


def read_workbook(path: Path) -> dict[str, pd.DataFrame]:
    """Read the input as text (nothing is changed or guessed by pandas) and return
    {sheet name: DataFrame}. Accepts the Excel workbook (.xlsx) or the Kaggle .csv.

    (Reading as text matters: Price stays '2.1' instead of a float, and
    Customer ID is not turned into 13085.0.)
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return read_csv_as_sheets(path)
    sheets = pd.read_excel(path, sheet_name=None, dtype=str, engine="openpyxl")
    return {name: _check_columns(name, df) for name, df in sheets.items()}


def save_raw(sheets: dict[str, pd.DataFrame], raw_dir: Path) -> list[Path]:
    """Write each sheet to data/raw/<sheet>.csv exactly as read. Re-runs overwrite."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name, df in sheets.items():
        slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
        p = raw_dir / f"raw_{slug}.csv"
        df.to_csv(p, index=False)
        out.append(p)
    return out


def combine(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Both sheets = one history. Remember where each row came from."""
    frames = []
    for name, df in sheets.items():
        d = df.rename(columns=RENAME).copy()
        d["source_sheet"] = name
        d["source_row"] = range(2, len(d) + 2)  # Excel row number (row 1 = header)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)
