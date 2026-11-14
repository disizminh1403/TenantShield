# TenantShield

A Streamlit classroom MVP for prospective Brooklyn renters, built for Wharton BEPP 2800.
Search the supplied scored cohort by address or exact BIN; inspect a building's **2026–27
probability of at least one recorded HPD heat/hot-water complaint**, historical counts,
registry characteristics, an on-demand interactive map and optional nearby Street View.

The score is a provisional **building-level estimate**, not an apartment's risk, a confirmed
heating failure or a safety guarantee. The application never retrains a model and does not
require an R installation or `.rds` file.

## Local setup (Windows PowerShell)

Use Python 3.11 or later. From this project directory:

```powershell
cd C:\Users\hoang_xthsvur\Documents\ChatGPT\TenantShield
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501**. No virtual-environment activation is required. Stop with Ctrl+C.
If `python` points to a nonworking Windows Store alias, this machine's existing interpreter is:

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m venv .venv
```

The installed Anaconda environment can also run the app directly (it already has the three runtime dependencies):

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m streamlit run app.py
```

macOS/Linux equivalent:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

## Optional Google Street View configuration

The map uses the **U.S. Census geocoder and OpenStreetMap**, with no API credential needed.
Google Geocoding is not required or used. Google geocodes are therefore never placed on a
non-Google map ([Google's geocoding policy](https://developers.google.com/maps/documentation/geocoding/policies)).

For optional imagery, enable **Street View Static API** and billing in your Google Cloud project.
Create a key restricted to that API and, when your hosting arrangement allows it, the server's
outbound IP addresses. Set conservative provider quotas and billing alerts. This is a
server-side key; browser HTTP-referrer restrictions are not appropriate for these requests.

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Edit the private `.streamlit/secrets.toml` locally to set `GOOGLE_MAPS_API_KEY`. Never commit
it, paste it into chat, or insert it into browser URLs. The real file is gitignored.
Alternatively set `GOOGLE_MAPS_API_KEY` in the process environment. Environment variables take
precedence over Streamlit Secrets. `.env.example` is reference documentation; `.env` is **not
automatically loaded**. Restart Streamlit after changing configuration.

All Google calls run on the server with timeouts. The UI receives image bytes, never the
key-bearing URL. Raw HTTP errors are suppressed because they may contain credentials.
Metadata is checked first; no image is requested for absent/denied metadata. An outdoor
panorama within roughly 50 m is requested, with heading toward the Census-derived point.
That point is approximate, so the image may not depict the actual façade. Unavailable,
quota-limited, denied and offline cases leave the building profile usable.

Google images are displayed uncropped with provider attribution. They are not written to
disk, decorated with a download control, or placed in a data/session cache; Streamlit holds
display media transiently. The image is cleared on the next rerun and must be explicitly
loaded again. Do not add persistent image caching, bulk fetching, or hidden prefetching.
Review [Street View policies](https://developers.google.com/maps/documentation/streetview/policies)
and [metadata documentation](https://developers.google.com/maps/documentation/streetview/metadata).
Public deployment also requires reviewing applicable provider terms and publishing an
operator-specific privacy notice/contact information; the app includes an educational-use
notice and provider privacy links.

## Data contract and inspected source

`TenantShield_App_Data.csv` is read without modification. To use another file set
`TENANTSHIELD_DATA_PATH` in Secrets or the environment (relative paths resolve from the project).
The app caches the validated CSV, invalidating when its size or modification time changes.

Actual inspected source: **135,367 rows, 11 columns**, unique BuildingID, one repeated full
address, no missing addresses/BINs/scores. Risk range: **0.020006095990538597–0.9930439591407776**.
Missing values: Zip 1, LegalClassA 108, LegalStories 54. No coordinates, history flags or R scripts
were supplied. Pipeline interpretation comes from `PROJECT_CONTEXT.md`; it was not independently
reconstructed from an R script.

| CSV field | Use |
| --- | --- |
| BuildingID | Required unique record identity, normalized as a string |
| BIN | Required column; exact lookup, kept as a string; shared BINs remain separate records |
| FullAddress | Required column; normalized case/spacing/punctuation and common street abbreviations for search |
| Zip | Display and selected-address geocoding |
| LegalClassA | Residential units; nonpositive/missing values shown as unavailable |
| LegalStories | Stories; nonpositive/missing values shown as unavailable |
| Construction Year | Footprint construction-year snapshot |
| PastComplaints_Clean | 2025–26 cleaned complaint count, per project handoff |
| Complaints2SeasonsAgo_Clean | 2024–25 cleaned complaint count, per project handoff |
| PredictedRisk | Required numeric probability in [0,1]; authoritative prediction |
| PredictedRiskPercent | Present but unused; UI formats PredictedRisk directly |

**History caveat:** History-availability flags are absent. A zero in a cleaned count may be
an imputed missing value; the UI displays **“0 / unknown”**, never asserts observed zero.
Missing counts are unavailable. Optional `HasPriorSeasonHistory` / `HasTwoSeasonsHistory`
columns are supported if a future export includes them. Neither missing history nor zero
complaints proves good building conditions. Date labels follow the deployment handoff, not
the computer clock. Coverage is the scored cohort, not every residential building in Brooklyn.

Validation rejects missing required columns, missing/duplicate BuildingIDs, malformed nonmissing
BINs, empty data and missing/nonfinite/out-of-bounds risk scores. Missing addresses are reported
but their records remain accessible by BIN. Invalid optional numeric metadata is reported and
shown as unavailable. Scientific-notation IDs are parsed using decimal arithmetic, never floats.
BIN `3000000` is a known placeholder, not a unique join key; selectors always use BuildingID.

## Search, mapping and privacy

Address searches are literal, case-insensitive partial matches with common abbreviations
(`St`, `Ave`, etc.) and numeric street ordinals normalized. They are not typo-tolerant fuzzy
searches. Exact address matches sort first. Ambiguous matches require an explicit selection;
large result sets show the first 200 and ask for a narrower query. No search calls an API.

**Locate this building** sends only the selected public CSV address to the
[U.S. Census geocoder](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html).
Census coordinates are interpolated along an address range, not verified building entrances.
Results outside a coarse Brooklyn-area bounding box are ignored; this is not a borough or
façade verification. Multiple geocoded candidates have a separate address selector. Census
responses are held in memory for 24 hours (maximum 512 entries); a shared process lock spaces
uncached calls by at least one second. No bulk geocoding exists.

The interactive OpenStreetMap embed loads only after a location request, includes attribution,
and delegates tile requests/caching to the browser. Network failure can leave the map blank;
an external larger-map link remains available. Review the
[OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/) before increasing
traffic; do not add prefetching/offline tile downloads. This setup is for a modest classroom
demo, not a distributed high-traffic service. Geocoding, map tiles and optional imagery require
internet access; local search and risk/history profiles work offline.

## Demo walkthrough

1. Launch and search **10 Jay St** (real source record: BIN **3000002**, BuildingID **316596**).
2. Its source prediction formats to **4.1%**. Explain that it concerns recorded building-wide complaints.
3. Note the **0 / unknown** history labels, and open Methodology & limitations.
4. Search **Jay St** to demonstrate multiple matches and explicit building selection.
5. Search by BIN **3000002** to return to the same record.
6. Click **Load map & Street View** with a configured key to load both in one action.
   Uncheck **Include nearby Street View** for a map-only lookup. Without a key, use **Locate this building**.
7. A single geocoder match is displayed immediately. Multiple geocoder matches require an explicit
   choice before showing the map; then use **Load Street View** for imagery. No imagery is fetched
   on search, selection or automatic reruns. Repeated image requests have a 10-second session cooldown.

## UI and risk interpretation

The selected building address is the page headline, with a large estimate and a comparison to
the actual median `PredictedRisk` in the loaded cohort. The comparison uses the displayed precision
(one decimal percentage point) and is explicitly a comparison of model scores, not observed rates,
an apartment-level probability or a safety threshold. No low/medium/high safety categories are used.
The CSV and prediction pipeline are unchanged.

The navy sidebar provides in-page navigation with outline icons. Inter typography, white cards,
subtle shadows and 16px corners sit on an off-white canvas. Red is a small brand accent, not a
risk classification; teal distinguishes historical counts. No Penn/Wharton logos or endorsement
claims are used. Inter loads from Google Fonts, with a system sans-serif fallback when offline.

The semicircular gauge is a continuous 0–100% scale driven directly by `PredictedRisk`, with no
category thresholds. Building characteristics and historical counts appear in compact cards
below the risk summary, followed by the side-by-side map and Street View. Narrow screens stack the cards and controls.
The location section reruns independently so its controls do not rerender the whole profile.
The existing 24-hour geocoder cache is preserved. Google imagery is still transient display media,
not persistently cached, and only an explicit load action makes an image request.

## How TenantShield Works

Open **How TenantShield Works** in the sidebar or beneath the dashboard's methodology heading.
The dedicated page explains the target, data sources, six final predictors, chronological
evaluation, exact supplied 2025–26 test metrics, and limitations. Its capture chart compares
56.3% top-decile recall with the approximately 10% theoretical expectation for random selection;
it does not claim a new random-selection experiment or future validation results.

The native Streamlit page is `pages/How_TenantShield_Works.py`; supporting content and HTML
figures are in `tenantshield/methodology.py`. It makes no geocoding or Google API calls and
does not read, score or modify the deployment CSV. Shared styling and sidebar navigation live
in `assets/style.css` and `tenantshield/design.py`. Run the same `streamlit run app.py` command.

## Community Cloud deployment preparation

See [DEPLOYMENT_AUDIT.md](DEPLOYMENT_AUDIT.md) for the verified file manifest,
prediction trace, memory measurements, and remaining deployment checks.
Use the repository root as this project folder and **app.py** as the main file.
Runtime dependencies are pinned in `requirements.txt`; no R, XGBoost installation,
model artifact, or Linux `packages.txt` is needed. Select Python 3.14 if offered
to match the locally tested interpreter (3.14.6); other Python versions require
a fresh dependency install and test run. The dependencies require Python >=3.11.

Include `TenantShield_App_Data.csv`, `tenantshield/`, `pages/`, `assets/`, and
`.streamlit/config.toml`. Configure the optional `GOOGLE_MAPS_API_KEY` through
Community Cloud's Secrets settings, never Git. Leave `TENANTSHIELD_DATA_PATH`
unset for the bundled CSV; do not copy a Windows absolute path into cloud settings.
Do not upload local virtual environments, screenshots, caches, or raw modeling data.
No deployment or GitHub push was performed during the audit.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q app.py tenantshield tests
```

Tests cover normalization, exact/partial search, ambiguous records, data validation, history
semantics, the actual supplied CSV, network/metadata failures, credential-safe errors and
Streamlit interactions. Service tests use synthetic fixtures/mocks explicitly; none of those
values are shown as real buildings. Google live success requires your private API configuration
and is not demonstrated by a passing mocked test.

Files: `app.py` (UI), `assets/style.css` and `tenantshield/design.py` (presentation only),
`tenantshield/data.py` (validation/search), `tenantshield/services.py` (server requests),
`tenantshield/maps.py` (OSM embed), `tests/` (regression checks).
