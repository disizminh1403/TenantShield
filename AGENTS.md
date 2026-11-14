# TenantShield — Coding Agent Instructions

Read `PROJECT_CONTEXT.md` before planning or changing implementation. Treat the attached CSV and R scripts as the source of truth for actual columns, values, preprocessing and prediction outputs. Do not assume any file exists unless observed.

## Mission
Build a polished but simple Streamlit MVP for prospective Brooklyn renters. Search by BIN or residential building address, look up precomputed XGBoost 2026–27 building complaint-risk predictions, display building metadata and selected historical complaint counts, geocode the selected building on demand, show a map, and optionally show Google Street View Static API imagery.

## Constraints
- Do not retrain XGBoost in the web app. `PredictedRisk` is already precomputed from the chosen model. The app must work without the `.rds` file.
- The model predicts whether a building receives >=1 **recorded HPD heat/hot-water complaint** in the season, not probability an individual renter experiences a heating failure.
- Model scores are provisional and may be miscalibrated. Label them as estimates; no guaranteed safety and no arbitrarily authoritative 'safe/unsafe' labels.
- Search the local CSV first. Never call geocoding for every row; call an API only for the user-selected building. BIN and BuildingID must be strings. Handle duplicate/ambiguous addresses with a building selector.
- Favor a free OpenStreetMap/Leaflet map display, with provider attribution and usage limits respected. Use Google Geocoding and Street View only if configured; provide a usable fallback without API credentials. Ensure all Google API use and storage respect provider terms and attribution.
- Never expose API keys client-side or commit them. Use Streamlit secrets/environment variables; include `.env.example`/`.streamlit/secrets.toml.example`, `.gitignore`, clear setup guidance. Do not request the real key in a chat transcript.
- Image metadata checks should precede requests; show 'Street View unavailable' when there is no suitable image. Nearby Street View is not guaranteed to depict the correct building façade.
- Validate CSV schema, numeric prediction bounds [0,1], no duplicate BuildingID, and missing addresses. Gracefully handle missing coordinates, geocoding/API errors, and network outages.
- No invented example predictions or coordinates presented as real buildings.
- Prefer modular, readable Python with minimal dependencies, helpful comments, and tests for search/lookup/schema normalization; provide `requirements.txt`, README and run instructions.
- Before implementing, inspect data columns and ask about *only* blocking gaps; otherwise make reasonable documented assumptions. Run available tests and lint/smoke checks, report what was verified.
