"""Run with: python -m streamlit run app.py"""

import os
import time
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from tenantshield.data import DataError, display_number, historical_count, load_data, normalize_address, search_buildings
from tenantshield.design import apply_design, explorer_sections, section
from tenantshield.maps import map_urls
from tenantshield.services import ServiceError, geocode, street_view


ROOT = Path(__file__).resolve().parent
SAMPLE_ADDRESS = "1035 WASHINGTON AVENUE, BROOKLYN"
SAMPLE_ID = "388518"
SAMPLE_BIN = "3029731"
st.set_page_config(page_title="TenantShield | Building Explorer", page_icon=":material/apartment:",
                   layout="wide", initial_sidebar_state="auto")


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

**How it was made.** The supplied project handoff describes XGBoost scoring using
complaint history, apartment counts and history-availability flags
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
        st.markdown(f"[Open larger map]({full}) · © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)")
        st.caption("Geocoding: U.S. Census Bureau. Use the larger-map link if the preview fails.")
        try:
            components.iframe(embed, height=330, scrolling=False)
        except st.errors.StreamlitAPIException:
            st.info("Map preview unavailable. Use the larger-map link above.")
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
                    try:
                        st.image(image.content, caption=f"Google Maps · {image.date} · {image.copyright}",
                                 width="stretch")
                    except (OSError, SyntaxError, ValueError):
                        st.warning("Street View unavailable — the returned image could not be displayed.")
            except ServiceError as exc:
                message = str(exc)
                st.warning(message if message.startswith("Street View unavailable") else f"Street View unavailable. {message}")
        else:
            st.info("Load a nearby image on demand. Imagery is supplied by Google Maps.")


def profile(row: pd.Series, cohort_median: float) -> None:
    st.header(row.FullAddress or "Address unavailable")
    st.markdown(''.join(f'<span class="ts-badge">{escape(label)}</span>' for label in [
        f"BIN {row.BIN or 'unavailable'}", f"Building ID {row.BuildingID}",
        f"Brooklyn, NY {row.get('Zip') or ''}", "2026–27 heating season",
    ]), unsafe_allow_html=True)
    with st.container(border=True, key="risk_summary"):
        section("Precomputed building estimate", "risk", "risk-assessment")
        st.markdown(f"#### {row.PredictedRisk:.1%} estimated chance of a recorded complaint")
        st.write("At least one recorded heat or hot-water complaint for this building during the 2026–27 heating season.")
        st.write(f"{cohort_median:.1%} median estimate across Brooklyn buildings scored by TenantShield.")
        st.caption("The median is calculated from the model scores in the scored cohort.")
        st.markdown('<div class="ts-risk-note">This is a building-level estimate. Conditions can vary by apartment, '
                    'and the estimate may be too high or too low.</div>', unsafe_allow_html=True)
    history, details = st.columns(2, gap="medium")
    with history, st.container(border=True, key="history_card"):
        section("Complaint history", "history", "complaint-history")
        for season, count, flag in (
            ("2025–26", "PastComplaints_Clean", "HasPriorSeasonHistory"),
            ("2024–25", "Complaints2SeasonsAgo_Clean", "HasTwoSeasonsHistory"),
        ):
            result = historical_count(row, count, flag)
            st.metric(f"{season} season", "Record status uncertain" if result == "0 / unknown" else result)
            if result == "0 / unknown":
                st.caption("The available data cannot distinguish between no recorded complaints "
                           "and missing records for this season.")
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
    with st.container(border=True, key="viewing_question"):
        section("What to ask at a viewing", "method", "viewing-question")
        st.write("Did residents experience any interruptions to heat or hot water last winter?")
    location_panel(row)


def submit_search() -> None:
    st.session_state.lookup_query = st.session_state.search_input.strip()
    st.session_state.pop("lookup_selected", None)


def change_search_mode() -> None:
    st.session_state.lookup_mode = st.session_state.search_mode
    st.session_state.search_input = ""
    submit_search()


def open_sample() -> None:
    st.session_state.lookup_mode = st.session_state.search_mode = "Address"
    st.session_state.lookup_query = st.session_state.search_input = SAMPLE_ADDRESS
    st.session_state.lookup_selected = SAMPLE_ID


def main() -> None:
    apply_design()
    st.title("Check a building’s heating history before you rent.")
    st.markdown("Look up a Brooklyn address to see the building’s recorded heat and hot-water complaints, "
                "its estimated chance of a complaint in the 2026–27 heating season, and what to ask at your viewing.")
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
    for warning in warnings:
        st.warning(warning)
    sample = search_buildings(data, SAMPLE_ADDRESS)
    sample = sample.loc[sample._address.eq(normalize_address(SAMPLE_ADDRESS))]
    sample_available = list(sample.index) == [SAMPLE_ID] and sample.iloc[0].BIN == SAMPLE_BIN
    state = st.session_state
    state.setdefault("search_mode", state.get("lookup_mode", "Address"))
    state.setdefault("search_input", state.get("lookup_query", ""))
    with st.container(border=True, key="search_card"):
        section("Find a building", "search", "search")
        mode = st.radio("Search by", ["Address", "BIN"], horizontal=True, key="search_mode",
                        on_change=change_search_mode)
        with st.form("building_lookup", border=False):
            st.text_input("Brooklyn address" if mode == "Address" else "Building Identification Number (BIN)",
                          placeholder="Enter a Brooklyn address" if mode == "Address" else "Enter the full 7-digit BIN",
                          max_chars=160, key="search_input")
            search_action, sample_action = st.columns(2, gap="small")
            search_action.form_submit_button("Search", type="primary", width="stretch", on_click=submit_search)
            sample_action.form_submit_button("Try a sample building", width="stretch", on_click=open_sample,
                                             disabled=not sample_available)
        st.caption("Partial street addresses and common abbreviations are supported. BIN matches are exact.")
    st.write("A quick viewing can tell you how an apartment looks today. A building’s complaint history can help "
             "you ask whether residents had trouble with heat or hot water last winter.")
    query = state.get("lookup_query", "")
    if query:
        matches = search_buildings(data, query, mode)
        if matches.empty:
            st.info("No matching building in the scored dataset. Try a shorter street address or check the full BIN. "
                    "This dataset does not cover every Brooklyn building.")
            if sample_available:
                st.button("Try a sample building", key="sample_recovery", on_click=open_sample)
        else:
            if mode == "BIN" and query.strip() == "3000000":
                st.warning("This is a placeholder BIN. Select the correct BuildingID; it is not a unique building identifier.")
            st.caption(f"{len(matches):,} matching building{'s' if len(matches) != 1 else ''}")
            if len(matches) > 200:
                st.info("Showing the first 200 matches. Add a house number or more of the street name to narrow your search.")
            options = matches.index[:200].tolist()
            previous = state.get("lookup_selected")
            selected = options[0] if len(matches) == 1 else st.selectbox(
                "Choose a building", options, index=options.index(previous) if previous in options else None,
                placeholder="Select the address and building ID…",
                key=f"building_choice_{mode}_{query}",
                format_func=lambda bid: f"{data.loc[bid, 'FullAddress'] or 'Address unavailable'} · BIN {data.loc[bid, 'BIN']} · ID {bid}")
            state.lookup_selected = selected
            if selected is not None:
                explorer_sections()
                profile(data.loc[selected], float(data.PredictedRisk.median()))
    st.divider()
    methodology()


if __name__ == "__main__":
    main()
