"""Run with: python -m streamlit run app.py"""

import os
import time
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from tenantshield.data import DataError, display_number, historical_count, load_data, search_buildings
from tenantshield.design import apply_design, gauge_svg, section
from tenantshield.maps import map_urls
from tenantshield.services import ServiceError, geocode, street_view


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="TenantShield | Building intelligence", page_icon=":material/apartment:", layout="wide")


def setting(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is not None:
        return value.strip()
    try:
        return str(st.secrets.get(name, default)).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


@st.cache_data(show_spinner=False)
def cached_data(path: str, modification: int, size: int):
    return load_data(path)


@st.cache_data(ttl=86400, max_entries=512, show_spinner=False)
def selected_location(address: str):
    return geocode(address)


def methodology() -> None:
    section("Behind the estimate", "method", "methodology")
    st.page_link("pages/How_TenantShield_Works.py", label="How TenantShield Works", icon=":material/menu_book:")
    with st.expander("Methodology & limitations"):
        st.markdown("""
**What is estimated?** The chance that a building receives at least one recorded
HPD heat/hot-water complaint in the **2026–27 heating season**. This is a building-level
estimate, not an individual apartment's risk, a confirmed heating failure or a safety rating.

**How it was made.** XGBoost scores were computed before this app was built. The supplied
project handoff describes complaint history, apartment counts and history-availability flags
as predictors, with the fixed model refit on 2022–23 through 2025–26 for deployment.
The app reads `PredictedRisk` directly; it does not train or alter the model.

**Interpret with care.** Scores are provisional and may be miscalibrated. The handoff reports
underprediction in held-out 2025–26 test deciles. Reporting behavior, building size, historical
coverage and current-registry selection affect these estimates. The scored cohort may omit
newly eligible buildings. Building characteristics may be historical snapshots.

**History has gaps.** The supplied CSV has cleaned counts but no history-availability flags.
A cleaned zero can be an observed zero or an imputed missing value. Neither zero complaints
nor a small predicted score guarantees reliable heat. Use these estimates alongside an
inspection, current records and conversations with tenants.

**Sources.** Supplied TenantShield prediction CSV and project handoff; underlying data from
[NYC HPD complaints](https://data.cityofnewyork.us/resource/ygpa-z7cr),
[HPD buildings](https://data.cityofnewyork.us/resource/kj4p-ruqc) and
[NYC building footprints](https://data.cityofnewyork.us/resource/5zhs-2jue).
        """)
    with st.expander("Privacy & map providers"):
        st.markdown("""
Searches run against the local CSV. **Locate this building** or **Load map & Street View** sends only the selected public
building address to the U.S. Census geocoder. Results are cached in server memory for up to
24 hours. Opening a map contacts OpenStreetMap from your browser. Including Street View or clicking **Load Street View** sends
the selected coordinates to Google through this app's server. Google imagery is displayed
for that interaction, without a persistent image cache or download feature.

Provider terms and privacy policies:
[U.S. Census](https://www.census.gov/about/policies/privacy.html) ·
[OpenStreetMap](https://osmfoundation.org/wiki/Privacy_Policy) ·
[Google](https://policies.google.com/privacy) ·
[Google Maps terms](https://maps.google.com/help/terms_maps/).
TenantShield is an educational prototype and provides no guarantee of building conditions.
        """)


@st.fragment
def location_panel(row: pd.Series) -> None:
    building_id = row.BuildingID
    section("Location & street context", "location", "building-location")
    if not row.FullAddress:
        st.info("Location unavailable: this record has no address.")
        return
    zip_code = str(row.get("Zip", "")).strip()
    zip_code = "" if zip_code.lower() in {"nan", "na", "none"} else zip_code
    address = f"{row.FullAddress}, NY {zip_code}".strip()
    key = setting("GOOGLE_MAPS_API_KEY")
    include_image = False
    if key:
        include_image = st.checkbox("Include nearby Street View", value=True, key="include_street_view",
                                    help="One metadata check and, if available, one image request per explicit load. No automatic refresh.")
    label = "Load map & Street View" if include_image else "Locate this building"
    requested = st.button(label, key=f"locate_{building_id}", type="primary")
    st.caption("On demand only · Map lookups cached for 24 hours · No background image requests")
    if requested:
        try:
            with st.spinner("Finding this address with the U.S. Census geocoder…"):
                locations = selected_location(address)
            st.session_state["location_result"] = (building_id, locations)
        except ServiceError as exc:
            st.session_state.pop("location_result", None)
            st.warning(str(exc))
    result = st.session_state.get("location_result")
    if not result or result[0] != building_id:
        st.info("Your building profile is ready. Request its location to view the map and nearby imagery.")
        return
    locations = result[1]
    if not locations:
        st.info("Map unavailable: no suitable address match was returned. The building profile is still available.")
        return
    if len(locations) == 1:
        location = locations[0]
        st.caption(f"Address match: {location.address}")
    else:
        location = st.selectbox("Confirm the geocoded address", locations, index=None,
                                format_func=lambda item: item.address, key=f"geo_{building_id}",
                                placeholder="Choose the matching address before viewing imagery…")
        if location is None:
            st.info("More than one location matched. Choose the correct address to continue.")
            return
    st.caption("Approximate location · Census address-range interpolation, not a verified entrance or façade.")
    map_column, street_column = st.columns(2, gap="medium")
    with map_column, st.container(border=True, key="map_card"):
        section("Interactive map", "location")
        embed, full = map_urls(location)
        components.iframe(embed, height=330, scrolling=False)
        st.markdown(f"[Open larger map]({full}) · © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)")
        st.caption("Geocoding: U.S. Census Bureau. If tiles do not load, use the larger-map link or try again later.")
    with street_column, st.container(border=True, key="street_card"):
        section("Nearby Street View", "street")
        st.caption("Nearby imagery may show a different façade and may be out of date.")
        if not key:
            st.info("Street View unavailable — optional Google API access is not configured.")
            return
        # A single unambiguous match can use the same explicit load gesture.
        load_image = requested and include_image and len(locations) == 1
        if not load_image:
            load_image = st.button("Load Street View", key=f"street_{building_id}")
        if load_image:
            last_request = st.session_state.get("street_last_request", float("-inf"))
            if time.monotonic() - last_request < 10:
                st.info("Please wait 10 seconds between image requests, then load again.")
                return
            st.session_state["street_last_request"] = time.monotonic()
            try:
                with st.spinner("Checking imagery availability…"):
                    image = street_view(key, location)
                if image is None:
                    st.info("Street View unavailable — no suitable outdoor imagery was found nearby.")
                else:
                    # Pass bytes, never a key-bearing Google URL. No cache/session persistence.
                    st.image(image.content, caption=f"Google Maps · {image.date} · {image.copyright}",
                             width="stretch")
            except ServiceError as exc:
                st.warning(f"Street View unavailable. {exc}")
        else:
            st.info("Load a nearby image on demand. Imagery is supplied by Google Maps.")


def profile(row: pd.Series, cohort_median: float) -> None:
    st.markdown('<div class="ts-eyebrow">PROPERTY OVERVIEW / BROOKLYN</div>', unsafe_allow_html=True)
    st.title(row.FullAddress or "Address unavailable")
    st.markdown(''.join(f'<span class="ts-badge">{escape(label)}</span>' for label in [
        f"BIN {row.BIN or 'unavailable'}", f"Building ID {row.BuildingID}",
        f"Brooklyn, NY {row.get('Zip') or ''}", "2026–27 heating season",
    ]), unsafe_allow_html=True)
    with st.container(border=True, key="risk_summary"):
        section("Risk assessment", "risk", "risk-assessment")
        left, right = st.columns([1, 1.7], gap="large")
        with left:
            with st.container(key="risk_gauge"):
                st.markdown(gauge_svg(float(row.PredictedRisk)), unsafe_allow_html=True)
                st.metric("Estimated complaint probability", f"{row.PredictedRisk:.1%}")
            st.caption("2026–27 · Precomputed XGBoost estimate")
        with right:
            st.markdown("#### A building-level estimate, in context")
            st.write("The estimated chance of **at least one recorded HPD heat/hot-water complaint** "
                     "at this building during the season.")
            # Compare the displayed precision so near-ties don't read as contradictory.
            score, median = round(float(row.PredictedRisk) * 100, 1), round(cohort_median * 100, 1)
            comparison = "Above" if score > median else "Below" if score < median else "At"
            st.markdown(f"**{comparison} the scored-cohort median of {cohort_median:.1%}** "
                        "(rounded to one decimal place).")
            st.caption("This compares model scores within the supplied dataset; it is not a safety threshold "
                       "or an observed complaint rate.")
        st.markdown('<div class="ts-risk-note"><strong>Interpret with care.</strong> Scores are provisional and may be miscalibrated. '
                    'This is not an individual apartment’s risk, a confirmed heating failure or a guarantee of safe conditions.</div>',
                    unsafe_allow_html=True)
    details, history = st.columns(2, gap="medium")
    with details, st.container(border=True, key="building_facts"):
        section("Building details", "building", "building-details")
        columns = st.columns(3)
        for column, label, field in zip(columns, ["Residential units", "Stories", "Construction year"],
                                       ["LegalClassA", "LegalStories", "Construction Year"]):
            value = row.get(field)
            if pd.isna(value) or value is None or value <= 0:
                value = "Unavailable"
            elif field == "Construction Year":
                value = str(int(value))
            else:
                value = display_number(value)
            column.metric(label, value)
        st.caption("Registry / footprint snapshot. Missing or nonpositive characteristics are shown as unavailable.")
    with history, st.container(border=True, key="history_card"):
        section("Complaint history", "history", "complaint-history")
        first, second = st.columns(2)
        first.metric("2025–26 season", historical_count(row, "PastComplaints_Clean", "HasPriorSeasonHistory"))
        second.metric("2024–25 season", historical_count(row, "Complaints2SeasonsAgo_Clean", "HasTwoSeasonsHistory"))
        st.caption("“0 / unknown” means the cleaned source value is zero, but may represent missing history. "
                   "History-availability flags are absent from this CSV. No recorded complaints does not mean no heating issues.")
    location_panel(row)


def main() -> None:
    apply_design()
    st.markdown('<div class="ts-eyebrow"><span class="ts-accent"></span>TENANTSHIELD / PROPERTY INTELLIGENCE</div>'
                '<div class="ts-page-title">Clarity before the keys.</div>'
                '<div class="ts-page-subtitle">Heating complaint intelligence for your next Brooklyn address.</div>', unsafe_allow_html=True)
    path = Path(setting("TENANTSHIELD_DATA_PATH", str(ROOT / "TenantShield_App_Data.csv")))
    if not path.is_absolute():
        path = ROOT / path
    try:
        stamp = path.stat()
        with st.spinner("Loading building records…"):
            data, warnings = cached_data(str(path), stamp.st_mtime_ns, stamp.st_size)
    except (OSError, DataError) as exc:
        st.error(str(exc) if isinstance(exc, DataError) else "Data CSV not found or inaccessible. Check TENANTSHIELD_DATA_PATH.")
        st.stop()
    st.caption(f"{len(data):,} scored buildings · Brooklyn, New York · 2026–27 outlook")
    for warning in warnings:
        st.warning(warning)
    with st.container(border=True, key="search_card"):
        section("Find a building", "search", "search")
        search_mode, search_input = st.columns([1, 3], gap="medium")
        with search_mode:
            mode = st.radio("Search by", ["Address", "BIN"], horizontal=True)
        with search_input:
            query = st.text_input("Brooklyn address" if mode == "Address" else "Building Identification Number (BIN)",
                              placeholder="Try 10 Jay Street or Jay St" if mode == "Address" else "Enter the full 7-digit BIN",
                              max_chars=160, key=f"query_{mode}")
        st.caption("Partial street addresses and common abbreviations are supported. BIN matches are exact.")
    if query.strip():
        matches = search_buildings(data, query, mode)
        if matches.empty:
            st.info("No matching building in the scored dataset. Try a shorter street address or check the full BIN. "
                    "This dataset does not cover every Brooklyn building.")
        else:
            if mode == "BIN" and query.strip() == "3000000":
                st.warning("This is a placeholder BIN. Select the correct BuildingID; it is not a unique building identifier.")
            st.caption(f"{len(matches):,} matching building{'s' if len(matches) != 1 else ''}")
            if len(matches) > 200:
                st.info("Showing the first 200 matches. Add a house number or more of the street name to narrow your search.")
            options = matches.index[:200].tolist()
            selected = options[0] if len(matches) == 1 else st.selectbox(
                "Choose a building", options, index=None, placeholder="Select the address and building ID…",
                format_func=lambda bid: f"{data.loc[bid, 'FullAddress'] or 'Address unavailable'} · BIN {data.loc[bid, 'BIN']} · ID {bid}",
                key=f"building_{mode}_{query.strip()}")
            if selected is not None:
                profile(data.loc[selected], float(data.PredictedRisk.median()))
    else:
        st.markdown('<div class="ts-empty"><h1>Every address has a history.</h1>'
                    '<p>Start with a building address or BIN. See its estimated complaint probability, '
                    'the records behind it, and the street around it.</p></div>', unsafe_allow_html=True)
        a, b, c = st.columns(3)
        for column, title, text in [
            (a, "01 / Find", "Search a Brooklyn address or BIN in the scored dataset."),
            (b, "02 / Understand", "Read the estimate alongside complaint history and its limitations."),
            (c, "03 / Explore", "Locate the building and view nearby street imagery when available."),
        ]:
            with column, st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(text)
    st.divider()
    methodology()
    st.caption("TenantShield · Independent building intelligence · Estimates, not guarantees.")


if __name__ == "__main__":
    main()
