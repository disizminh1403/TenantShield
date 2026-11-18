# TenantShield Plus

An add-on to TenantShield that lives entirely in this `plus/` folder. It reuses the main app's
search, validation and styling, and leaves the main app, its CSV and its `PredictedRisk` untouched.

Run it from the repository root:

```sh
python -m streamlit run plus/app.py
```

It needs only the main app's dependencies (`requirements.txt`). No API key is required.

## What it adds

**Features**

| Page | What a renter can do |
| --- | --- |
| Building Check | See complaints recorded so far this season, three estimates, where the building ranks against Brooklyn, its ZIP and same-size buildings, six seasons of history, buildings within 150–400 m (table and optional map), tailored viewing questions and a downloadable summary |
| Building Check, live check | On one click, fetch today's HPD heat/hot-water complaints and open HPD violations for that one building from NYC Open Data |
| Compare Shortlist | Put up to four buildings side by side |
| Area Explorer | Compare ZIP codes, then list and sort the buildings in one ZIP |
| Evidence & Method | Read the backtests, calibration charts, model comparison, summary statistics and limitations |

**Predictions.** The original score answers "at least one recorded complaint?". Three companion
estimates, precomputed offline, add detail:

| Estimate | Column | Held-out 2025–26 result |
| --- | --- | --- |
| 5 or more recorded complaints in 2026–27 | `ChronicRisk` | ROC-AUC 0.951, PR-AUC 0.625; the top 10% of buildings held 87% of the buildings that reached 5+ |
| Expected number of recorded complaints | `ExpectedComplaints` | Mean absolute error 0.596 per building vs 0.608 for "same as last season"; the top 10% held 86% of all complaints |
| At least one more complaint by 31 May, given complaints since 1 October | `RestOfSeasonRisk` | PR-AUC 0.603 vs 0.582 without the in-season count |

All three were trained on outcome seasons 2023–24 and 2024–25, tested once on 2025–26, then refit
through 2025–26 to score 2026–27. Every input is measured before the window it predicts.
They are estimates of **recorded HPD complaints** for a building. They are not apartment-level
risks, verified failures or safety ratings, and they may be too high or too low.

## Findings worth knowing

- **The two history columns in `TenantShield_App_Data.csv` appear to cover different windows.**
  `PastComplaints_Clean` (2025–26) matches a 1 October–31 May count for 99.999% of buildings.
  `Complaints2SeasonsAgo_Clean` (2024–25) matches a 1 October–30 September count for 99.98% of
  buildings and a 1 October–31 May count for only 98.9%, so it seems to include June–September
  complaints (about 3,500 extra). If the original training panel was built the same way, earlier
  seasons were labelled on 12 months and the latest on 8. This is worth checking in the R/Power Query
  pipeline. Plus counts every season from 1 October to 31 May and shows June–September separately.
- **The original score is holding up this season.** From 1 October to 17 November 2026, 4,324 scored
  buildings recorded a complaint; the top 10% by `PredictedRisk` contain 75% of them (ROC-AUC 0.896).
  This is a ranking check on a partial season, not a calibration test.
- **The rebuilt data agrees with the original model.** A Python gradient-boosting model refit on the
  original six inputs correlates 0.998 with the R/XGBoost `PredictedRisk`.
- **Model family matters less than inputs.** On the same inputs, random forest, gradient boosting and
  logistic regression score within about 0.01 PR-AUC of each other. Adding a third season, apartment and
  building-wide detail, summer complaints and building characteristics lifts PR-AUC from 0.577 to 0.608.
- **Complaints are concentrated.** In 2025–26, 2.9% of buildings recorded 5 or more complaints and
  produced 82% of all complaints.

## Files

| Path | Role |
| --- | --- |
| `app.py`, `pages/` | Streamlit pages |
| `tsplus/store.py` | Loads and validates the Plus table, joins it to the main CSV, peer and nearby comparisons |
| `tsplus/live.py` | On-demand NYC Open Data lookups for one building |
| `tsplus/report.py` | Viewing questions and the downloadable summary |
| `tsplus/charts.py`, `tsplus/ui.py`, `assets/plus.css` | Charts, page shell, extra styles |
| `data/plus_predictions.csv` | One row per BuildingID: the three estimates, season-to-date counts, six seasons of counts, tax-lot coordinates |
| `data/plus_report.json` | Backtest results and summary statistics shown on the Evidence page |
| `pipeline/` | Offline scripts that produce the two data files |
| `tests/` | Unit and app tests |

## Rebuilding the data

The app never trains a model. To refresh the snapshot or retrain offline:

```sh
python -m pip install -r plus/pipeline/requirements.txt
python plus/pipeline/fetch_open_data.py       # about 5 minutes; writes plus/raw_data/ (gitignored)
python plus/pipeline/build_predictions.py     # about 7 minutes; writes plus/data/
```

`fetch_open_data.py` downloads three public NYC Open Data extracts: HPD heat/hot-water complaints for
Brooklyn since October 2020 (`ygpa-z7cr`), the HPD building registry (`kj4p-ruqc`) and PLUTO tax-lot
coordinates (`64uk-42ks`). Coordinates come from joining registry block and lot to PLUTO, a bulk join
rather than geocoding, and cover 99.7% of the cohort.

The companion models use scikit-learn `HistGradientBoosting` with the handoff's settings where an
equivalent exists (300 trees, depth 4, learning rate 0.03, minimum leaf 20). XGBoost was not used
because it needs an OpenMP runtime that was not installed on the build machine. The count model fits
log(1 + complaints) and rescales to the training total; a Poisson objective diverged on the largest buildings.

## Configuration

All optional, read from environment variables first and then `.streamlit/secrets.toml`:

| Setting | Purpose |
| --- | --- |
| `GOOGLE_MAPS_API_KEY` | Enables the on-demand Street View button, as in the main app |
| `NYC_OPEN_DATA_APP_TOKEN` | Raises NYC Open Data rate limits for the live check; sent as a header from the server only |
| `TENANTSHIELD_DATA_PATH`, `TENANTSHIELD_PLUS_DATA_PATH`, `TENANTSHIELD_PLUS_REPORT_PATH` | Alternative file locations |

Never commit keys or tokens. To deploy on Streamlit Community Cloud as a second app, set the main
file to `plus/app.py`.

## Privacy and providers

- Search, comparisons, nearby buildings and the area pages use only local files.
- **Check today's HPD records** sends one BuildingID to NYC Open Data from the server, on click, cached for an hour. Apartment numbers are not kept or shown.
- **Show these buildings on a map** loads CARTO basemap tiles (© CARTO, © OpenStreetMap contributors) in the browser, only after the toggle is switched on.
- **Load nearby Street View** behaves as in the main app: a metadata check, then at most one image, never cached.

## Tests

```sh
python -m pytest plus/tests      # 30 tests
python -m ruff check plus
```

## Limitations

Complaints are reports and depend on tenants choosing to call 311. One apartment can file many
complaints. Large buildings pass 5 complaints far more easily than small ones. A cold winter raises
complaints everywhere, and all backtests ran slightly low for 2025–26 for that reason. Today's
building list is applied to past seasons. Locations are approximate tax-lot points. The companion
models are a separate Python build and have not been reviewed as part of the original R model.
