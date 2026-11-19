"""Settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# MySQL by default. Example: mysql+pymysql://user:password@localhost:3306/retail
DATABASE_URL = os.getenv(
    "DATABASE_URL", "mysql+pymysql://root:password@127.0.0.1:3306/retail"
)

DEFAULT_EXCEL = ROOT / "data" / "online_retail_II.xlsx"
RAW_DIR = ROOT / "data" / "raw"
REF_DIR = ROOT / "data" / "reference"
FX_CSV = REF_DIR / "fx_rates_gbp_usd.csv"
COUNTRY_CSV = REF_DIR / "country_region.csv"
NON_PRODUCT_CSV = REF_DIR / "non_product_codes.csv"

STATS_JSON = ROOT / "data" / "run_stats.json"
RESULTS_MD = ROOT / "RESULTS.md"

PLACEHOLDER_CUSTOMER = "GUEST"  # R3: all blank Customer IDs
