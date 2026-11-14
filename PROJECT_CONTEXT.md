# TenantShield — Project Handoff for Codex

## Product goal
TenantShield is a Wharton BEPP 2800 final-project startup MVP aimed at reducing information asymmetry for prospective renters in Brooklyn, NYC. Users search by building address or BIN and see the model-estimated risk of at least one recorded heating/hot-water complaint during NYC's 2026–27 heating season, along with historical indicators, building information, map location and optional nearby Google Street View imagery.

## Data sources and pipeline
The project uses NYC public datasets processed through Excel Power Query and R:
1. HPD heat/hot-water complaints (`ygpa-z7cr`); initial subset ~418,506 raw problem rows. Aggregated by unique complaint ID, BuildingID and heating season.
2. HPD Buildings Subject to HPD Jurisdiction (`kj4p-ruqc`); ~138,386 Brooklyn current/active building records, with BuildingID, BIN, address, LegalClassA (residential apartment count), LegalStories, Zip and building type.
3. HPD Housing Maintenance Code Violations (`wvxf-dwi5`); heating/hot-water violation history, including Class C. Tested but omitted from final simpler model due to near-zero incremental value.
4. NYC Building Footprints (`5zhs-2jue`); BIN and Construction Year, focusing on Feature Code 2100 with unique valid BINs. Applied conservative historical eligibility rule: constructed before the prediction season's starting year; this is only a proxy for historical presence/occupancy.

Panel: one BuildingID × heating season; 2022–23 to 2025–26 historical modeling panel = 540,404 observations. Positive Y = at least 1 recorded complaint in the outcome season. The final held-out test season 2025–26 contains 135,367 buildings (13,326 positives, 9.84%). Historical data and present-day registry introduce coverage/selection and look-ahead limitations; do not overclaim.

## Features/model
Main final model: XGBoost binary classifier implemented in R tidymodels with `boost_tree()`, XGBoost engine, 300 trees, depth 4, learning rate .03, min_n=20, loss_reduction=0, sample_size=.8. Predictors:
- PastComplaints_Clean (previous heating season)
- Complaints2SeasonsAgo_Clean
- LogUnits = log1p(LegalClassA), imputing nonpositive/missing apartment counts with median from training
- MissingUnits
- HasPriorSeasonHistory
- HasTwoSeasonsHistory

Historical missing counts were imputed with zero FOR MODELING ONLY and history flags retained. Never treat absence of history as proof of zero complaints. Violation features omitted from final XGBoost 1. No outcome-season `HeatComplaints` or Y as predictors.

Time split: train seasons 2022–23/2023–24; validation 2024–25; untouched test 2025–26. Locked model subsequently refit on 2022–23 through 2024–25 and evaluated once on 2025–26. Test metrics: PR-AUC .592, ROC-AUC .836, Log Loss .219, Brier .0585; among top 10% highest-risk buildings, 7,501/13,326 positive cases captured (56.3% recall) with 55.4% precision. Test decile calibration showed underprediction, e.g. highest decile mean predicted 50.7% vs actual 55.4%. Scores are estimates, not guarantees, and should not be portrayed as perfectly calibrated.

For 2026–27 deployment, refit fixed XGBoost model on 2022–23 through 2025–26; shift history to previous 2025–26 and two seasons prior 2024–25. The current scored cohort is 135,367 BuildingIDs, zero missing PredictedRisk; min predicted risk .0200, median .0288, max .993. This cohort comes from eligible 2025–26 buildings, and can omit newly eligible 2026–27 buildings. Verify before claiming full coverage. Some historical snapshot features may not reflect contemporaneous values.

## Available/expected files (inspect actual directory; names are examples)
- `TenantShield_App_Data.csv`: desired slim building-level lookup with BIN, BuildingID, FullAddress, PredictedRisk, housing characteristics and historical indicators. If not supplied, derive from `TenantShield_2026_Predictions_Working.csv` or model-ready dataset, NEVER invent values.
- `TenantShield_2026_Predictions_Working.csv`: possible full scored table.
- `TenantShield_Model_Ready.csv`: historical modeling panel, not directly suitable for current-season app without building-level selection.
- `TenantShield_Deployment_XGBoost.rds`: R model artifact if available; not needed for precomputed-risk app.
Note the exact names/columns vary; inspect source files first. BIN has been read as numeric in R before; normalize to string avoiding scientific notation. Expected `FullAddress` and `PredictedRisk` exist. Latitude and Longitude were NOT present in the inspected deployment table.

## MVP functionality & technical approach
- Stack: Python + Streamlit, pandas, small mapping component (e.g. folium/streamlit-folium or native Streamlit map), Google Geocoding on demand for a selected address, Google Street View Static API for street-level imagery if configured.
- Local lookup: user searches BIN (exact match) or address (case-insensitive normalized match, fuzzy/partial results with a disambiguation picker). Do not send arbitrary search text to Google before matching to a known building.
- Display prediction prominently with season label `2026–27`; clarify it concerns at least one recorded building-wide complaint (not an apartment-level risk). Avoid unsupported Low/Medium/High hazard thresholds; optional relative percentile rank within eligible cohort if calculated correctly.
- Display building information: normalized address, BIN, apartment count, floors, construction year if supplied; past complaints from 2025–26 and two seasons prior 2024–25. Keep year labels explicit and avoid stale outcome labels.
- Map: geocode the chosen address ON DEMAND; draw pin with confidence warning if ambiguous/approximate. Google Street View (if enabled) fetch metadata first, handle absent pano and set heading appropriately where possible; preserve Google attribution, caching, and licensing requirements. Street View may show nearby panorama rather than the exact building.
- Handle missing API key/failed geocoding gracefully: building risk profile still renders; map/image show informative fallback. Allow optional OSM geocoding if compliant with provider policies but avoid exceeding public Nominatim rate limits or using it for bulk geocoding.
- Optimize for a classroom demo: clear layout, responsive interactions, caching the CSV lookup, limited calls, clean setup README and basic tests.

## Known pitfalls and research limitations
- BIN 3000000 is a placeholder and should not be used as a unique join key.
- HouseNumber may include values such as `447A`; treat it as text. Earlier Power Query converted these to numeric and caused data errors.
- Building Footprints feature code 2100 represents buildings, but available construction year is approximate; year-only cutoff is a conservative proxy.
- Present-day HPD building register can introduce survivor/selection bias; complaint reporting varies by building size and tenants.
- The app should not make unsupported safety claims or imply that 0 recorded complaints means 0 actual heating issues.
- Secrets: never commit billing credentials; avoid adding key to code or logs. Implement tight API quotas and graceful failure.

## Delivery expectation
Working Streamlit source, requirements, README, example secrets file, tests and demo instructions. Demonstrate app with real input CSV when available, and report exact files tested, any missing source columns and API dependencies. Do not fabricate a functional integration if API key is unavailable; provide a well-defined integration path and fallback UI.
