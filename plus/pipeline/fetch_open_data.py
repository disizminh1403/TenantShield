"""Download the public NYC Open Data extracts used by the TenantShield Plus pipeline.

Run from the repository root:  python plus/pipeline/fetch_open_data.py

These are bulk dataset downloads (not geocoding calls). Output goes to
plus/raw_data/, which is gitignored. No API key is needed; requests are paged
and paced to stay well inside anonymous Socrata limits.
"""

from io import StringIO
from pathlib import Path
import sys
import time

import pandas as pd
import requests


RAW = Path(__file__).resolve().parents[1] / "raw_data"
BASE = "https://data.cityofnewyork.us/resource/{}.csv"
PAGE = 50_000
# Complaint history starts two seasons before the first training target so that
# lagged features exist for every modeled season.
HISTORY_START = "2020-10-01T00:00:00"

EXTRACTS = {
    # HPD complaints and problems: one row per problem; several problems can share a complaint.
    "complaints": ("ygpa-z7cr", {
        "$select": "problem_id,complaint_id,building_id,bin,received_date,apartment,unit_type,"
                   "problem_code,complaint_status,post_code,nta",
        "$where": f"borough='BROOKLYN' AND major_category='HEAT/HOT WATER' AND received_date>='{HISTORY_START}'",
        "$order": "problem_id",
    }),
    # HPD building registry: block and lot let us attach a tax-lot location.
    "buildings": ("kj4p-ruqc", {
        "$select": "buildingid,bin,block,lot,zip,communityboard,managementprogram,recordstatus",
        "$where": "boroid='3'",
        "$order": "buildingid",
    }),
    # PLUTO: one approximate coordinate per tax lot (BBL).
    "pluto": ("64uk-42ks", {
        "$select": "bbl,latitude,longitude",
        "$where": "borough='BK' AND latitude IS NOT NULL",
        "$order": "bbl",
    }),
}


def download(name: str, dataset: str, params: dict) -> pd.DataFrame:
    pages, offset = [], 0
    while True:
        for attempt in range(4):
            try:
                response = requests.get(BASE.format(dataset), params={**params, "$limit": PAGE, "$offset": offset},
                                        timeout=(10, 180), headers={"User-Agent": "TenantShield-Classroom-MVP/1.0"})
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        page = pd.read_csv(StringIO(response.text), dtype=str, keep_default_na=False)
        pages.append(page)
        print(f"  {name}: {offset + len(page):,} rows", flush=True)
        if len(page) < PAGE:
            return pd.concat(pages, ignore_index=True)
        offset += PAGE
        time.sleep(1)


def main(names: list[str]) -> None:
    RAW.mkdir(exist_ok=True)
    for name in names or list(EXTRACTS):
        dataset, params = EXTRACTS[name]
        frame = download(name, dataset, params)
        frame.to_csv(RAW / f"{name}.csv", index=False)
        print(f"Saved {name}: {len(frame):,} rows")


if __name__ == "__main__":
    main(sys.argv[1:])
