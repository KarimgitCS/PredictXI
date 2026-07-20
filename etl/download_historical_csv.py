"""
Downloads the 10 football-data.co.uk Premier League season CSVs into
data/raw/.

Usage:
    python etl/download_historical_csv.py

Safe to re-run — just re-downloads and overwrites each file.
"""

import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Must match the (filename, season) pairs in load_historical_csv.SEASON_FILES.
SEASON_CODES = ["1011", "1112", "1213", "1314", "1415", "1516", "1617", "1718", "1819", "1920"]


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for code in SEASON_CODES:
        url = f"{BASE_URL}/{code}/E0.csv"
        dest = RAW_DIR / f"E0_{code}.csv"
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            sys.exit(f"Failed to download {url}: {exc}")
        dest.write_bytes(response.content)
        line_count = response.text.count("\n")
        print(f"{code}: saved {dest} ({line_count} lines)")


if __name__ == "__main__":
    main()
