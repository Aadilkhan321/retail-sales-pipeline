"""One command runs the whole pipeline:

    python -m pipeline.run --input data/online_retail_II.csv
"""
import argparse
import json
import time
from pathlib import Path

import pandas as pd

from . import config, db, extract, load, results, rules


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Retail sales ETL: Excel -> clean -> MySQL")
    ap.add_argument("--input", "--excel", dest="excel", type=Path, default=config.DEFAULT_EXCEL,
                    help="the Excel workbook (.xlsx) or the Kaggle online_retail_II.csv")
    ap.add_argument("--database-url", default=None, help="SQLAlchemy URL (default: env DATABASE_URL, see config.py)")
    ap.add_argument("--raw-dir", type=Path, default=config.RAW_DIR)
    ap.add_argument("--no-results", action="store_true", help="do not write RESULTS.md")
    args = ap.parse_args(argv)

    log(f"Reading {args.excel} (the real file takes a few minutes)")
    sheets = extract.read_workbook(args.excel)

    log("Part 1: saving untouched raw copy")
    for p in extract.save_raw(sheets, args.raw_dir):
        log(f"  wrote {p}")
    raw = extract.combine(sheets)
    log(f"  {len(raw):,} rows read from {len(sheets)} sheets")

    log("Part 2: cleaning (R1-R8)")
    non_product = pd.read_csv(config.NON_PRODUCT_CSV, dtype=str)
    country_map = pd.read_csv(config.COUNTRY_CSV, dtype=str)
    fx = rules.load_fx(config.FX_CSV)
    df, issues, country_map, stats = rules.clean(raw, non_product, fx, country_map)
    config.STATS_JSON.write_text(json.dumps(stats, indent=2))
    log(f"  {stats['rows_loaded']:,} rows kept, {len(issues):,} issues logged")

    log("Part 3: loading into the database (tables are rebuilt, so re-runs never duplicate)")
    db.ensure_database(args.database_url)
    engine = db.get_engine(args.database_url)
    tables = load.build_tables(df, country_map, issues)
    load.load_all(engine, tables)
    for name, t in tables.items():
        log(f"  {name}: {len(t):,} rows")

    if not args.no_results:
        results.write_results_md(engine)
        log(f"Wrote {config.RESULTS_MD}")
    log("Done.")


if __name__ == "__main__":
    main()
