# TenantShield deployment audit

Audited locally on 2026-11-13. No push, commit, deployment, training, scoring,
UI change, or CSV modification was performed.

## Entrypoint and required files

Select `app.py` as the Streamlit main file, with this project as repository root.
All required files below were observed locally; none is missing.

| File | Runtime role |
| --- | --- |
| `app.py` | Main dashboard and server-side settings |
| `TenantShield_App_Data.csv` | Authoritative precomputed building predictions |
| `tenantshield/__init__.py` | Package marker |
| `tenantshield/data.py` | CSV validation, normalization, search |
| `tenantshield/services.py` | Census and Google server requests |
| `tenantshield/maps.py` | OpenStreetMap embed URLs |
| `tenantshield/design.py` | Shared design and page links |
| `tenantshield/methodology.py` | Methodology content and figures |
| `pages/How_TenantShield_Works.py` | Secondary Streamlit page |
| `assets/style.css` | Shared styles |
| `.streamlit/config.toml` | Theme and navigation configuration |
| `requirements.txt` | Runtime dependencies |

Also retain README, this audit, `.gitignore`, secret examples, project context,
tests, `pyproject.toml`, and `requirements-dev.txt` for maintenance. They are not
runtime data inputs. Do not publish `.streamlit/secrets.toml`.

## Prediction trace and serialization

`app.py:main` resolves the CSV, calls `cached_data`, and then `data.load_data`.
`load_data` reads CSV fields as strings; `validate_data` validates identifiers,
converts `PredictedRisk` to numeric, checks bounds, and adds a search column.
The selected row reaches `profile`, which formats `row.PredictedRisk` as a
percentage and supplies the same value to the gauge. Cohort median is only
display context. `PredictedRiskPercent` is not used for the displayed estimate.

There is no model load, inference call, R subprocess, rpy2, XGBoost import,
pickle/joblib deserialization, or training code in runtime Python files.
No R script or model artifact was found. The upstream R/XGBoost procedure is
documented in PROJECT_CONTEXT.md but cannot be independently reconstructed
from this workspace. Missing training artifacts do not block this app.
Model serialization compatibility is therefore not applicable to deployment.

## Dependencies and paths

Only three direct third-party runtime dependencies are imported: Streamlit,
pandas, requests. Requirements now pin the tested installed versions:
Streamlit 1.58.0, pandas 3.0.3, requests 2.34.2. Standard-library imports require
no pip entries; pytest and ruff remain development-only. Streamlit installs its
transitive packages. This is a direct-dependency pin, not a complete lockfile.
No OS packages or `packages.txt` are needed by the inspected code.

Local tests used Anaconda Python 3.14.6 on Windows. Package metadata requires
Python >=3.11 overall. Select Python 3.14 if available to match local testing;
verify a clean Linux install before calling cloud compatibility proven.
The existing Anaconda environment passed `pip check`; a fresh Linux dependency
resolution and install was not performed in this audit.

CSV and CSS paths are rooted at `__file__`, using pathlib. Page links use exact
observed case and forward slashes. No Windows-only runtime paths were found.
README's Windows commands are local instructions, not runtime paths.
The private local secrets configuration has no data-path override. Leave
`TENANTSHIELD_DATA_PATH` unset in Cloud, or use a repository-relative path.

## Credentials and external services

`setting` checks the environment, then `st.secrets`. A local Google key is
configured; its value was not printed. No Google-key literal was found in
runtime source. Google requests run in `services.py`, metadata before imagery.
Only image bytes reach Streamlit, not key-bearing URLs. Raw requests exceptions
are replaced with generic errors. Images have no persistent application cache.
The actual secrets file is gitignored; no files are tracked and this repository
has no commits yet. There is no committed history here to inspect for exposure.

For Cloud, add the optional key in the app's Secrets settings. Enable Street
View Static API and billing; review API restrictions, quota and alerts.
The 10-second cooldown is per session, not a global billing limit. More users
can still generate more requests. Server IP restrictions must fit the cloud
host; do not assume your local IP applies. Cloud documents that its outbound
IPs may change. Missing/denied credentials leave the profile and free map usable.

Census geocoding and Google require outbound HTTPS; OSM embeds and Google Fonts
load in the browser. Fonts have a system fallback. Verify these providers after
eventual deployment. This audit did not issue paid Google calls or change keys.
The platform may override local configuration, including usage statistics.

## Data size and memory

CSV: 11,957,534 bytes (11.40 MiB), 135,367 rows, 11 source columns.
Validation succeeded without warnings. Validated DataFrame including normalized
search field: approximately 23.80 MiB (`memory_usage(deep=True)`). A standalone
loader process measured 123.61 MiB resident memory after loading; load took
7.78 seconds in this run. These are Windows observations, not cloud peak-memory
or concurrent-user benchmarks.

Streamlit's serialized data cache and per-session returned copies add memory,
as do parsing temporaries, search results, UI runtime, and transient images.
CSV cache has no entry bound; repeated source changes can retain old cache keys
until a cache clear/restart. The Census cache is bounded at 512 entries/24 hours.
Monitor actual cloud memory and concurrent sessions. No model is held in memory.
No large raw modeling datasets were found. Screenshots are already ignored.

CSV SHA-256, unchanged:
`5dbdb4b299e8021683f6180d17c8c1f91370336321c1e4fd430b2ebcb3c75498`

## Changes and verification

- `requirements.txt`: pin the three tested direct runtime versions.
- `.gitignore`: add common virtual environments, build/editor caches, raw-data
  directories, named full modeling tables, and R serialized model artifacts.
  The required app CSV and both configuration examples remain includable.
- `README.md`: add Cloud file/configuration/Python guidance and audit link.
- `DEPLOYMENT_AUDIT.md`: add this evidence and remaining checks.

Verification: **48 tests passed in 32.11 seconds**; ruff passed; compileall
passed for app, package, pages and tests; `pip check` found no broken requirements.
Tests cover actual CSV validation, search/risk display, page navigation, mocked
geocoding/Street View, failure handling and API cost controls. Git ignore checks
confirmed secrets, environments, caches and raw inputs are excluded, while
the required CSV and secrets template are not ignored. No new UI behavior needed
tests. Linux runtime, hosted resource use and live provider access remain untested.

## Before eventual deployment

1. Review which source/data files may be shared and create the repository commit
   only when ready. All project files are currently untracked; nothing was pushed.
2. Use `app.py`, the root requirements file and a supported Python version;
   perform a clean install and smoke test on the target host.
3. Set optional Cloud Secrets, provider restrictions and quotas. Do not copy
   local credentials into Git or use a Windows data path in Cloud.
4. Verify search, methodology navigation, on-demand Census map, Google image
   success/fallback, and memory with representative simultaneous visitors.
5. Review the operator privacy/contact notice and provider terms for public use.

Official references consulted:
- [App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Cloud status and limitations](https://docs.streamlit.io/deploy/streamlit-community-cloud/status)
