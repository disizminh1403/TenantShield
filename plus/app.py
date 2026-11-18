"""TenantShield Plus: building check.

Run from the repository root:  python -m streamlit run plus/app.py

Reads precomputed estimates only. No model is trained or loaded here.
"""

from datetime import date
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import pydeck as pdk  # noqa: E402
import streamlit as st  # noqa: E402

from tsplus import charts, live, store, ui  # noqa: E402
from tsplus.report import HEAT_RULES, HEAT_RULES_URL, text_summary, viewing_questions  # noqa: E402
from tenantshield import services  # noqa: E402
from tenantshield.data import search_buildings  # noqa: E402
from tenantshield.maps import map_urls  # noqa: E402

SAMPLE_ID = "388518"   # 1035 Washington Avenue: the same sample building as the main app
RADII = (150, 250, 400)


def percent(value: float) -> str:
    return "under 0.1%" if value < .001 else f"{value:.1%}"


def band_text(band: dict, joiner: str = "–") -> str:
    return f"{band['low']:.0%}{joiner}{band['high']:.0%}"


def rank_text(share: float, group: str = "scored Brooklyn buildings") -> str:
    """Never rounds up to 100%: a building cannot be higher than itself."""
    if share >= .99:
        return f"In the top 1% of {group}."
    return f"Higher than {math.floor(share * 100)}% of {group}."


def count_text(value: float) -> str:
    return "under 0.1" if value < .1 else f"about {value:,.1f}" if value < 20 else f"about {value:,.0f}"


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def cached_live(building_id: str, day: str):
    """One building, one explicit click, cached for an hour."""
    token = ui.setting("NYC_OPEN_DATA_APP_TOKEN")
    records = live.heat_complaints(building_id, date.fromisoformat(day), token)
    violations, truncated = live.open_violations(building_id, token)
    return records, violations, truncated


# ----------------------------------------------------------------------------------------------
# Profile sections
# ----------------------------------------------------------------------------------------------

def season_card(row: pd.Series, report: dict) -> None:
    through = ui.pretty_date(report["data_through"])
    with st.container(border=True, key="plus_season"):
        ui.section(f"This heating season so far ({report['deploy_season']})", "history", "season-so-far")
        first, second, third = st.columns(3)
        first.metric("Recorded complaints since 1 October", f"{int(row.SeasonToDate):,}")
        second.metric("Different apartments reporting", f"{int(row.SeasonToDateApartments):,}",
                      help="Apartment-level complaints only. Building-wide complaints are not tied to an apartment.")
        third.metric("Chance of at least one more by 31 May", percent(row.RestOfSeasonRisk),
                     help="Companion model: uses complaint history plus the complaints already recorded this season.")
        st.caption(f"Heat and hot-water complaints recorded by HPD from 1 October through {through}. "
                   "This is a saved snapshot of NYC Open Data, not a live feed.")
        band = store.band_for(report["backtest"]["rest_reliability"], row.RestOfSeasonRisk)
        if band:
            ui.note(f"<strong>How buildings like this turned out.</strong> At the same point in the "
                    f"{report['test_season']} season, {band['n']:,} buildings had an estimate between "
                    f"{band_text(band, ' and ')}. {band['observed_rate']:.0%} of them went on to record at least one more "
                    "complaint before 31 May.")
        live_panel(row)


@st.fragment
def live_panel(row: pd.Series) -> None:
    building_id = row.BuildingID
    requested = st.button("Check today's HPD records", key=f"live_{building_id}",
                          help="Sends only this BuildingID to NYC Open Data. Results are cached for one hour.")
    if requested:
        last = st.session_state.get("plus_live_clock", float("-inf"))
        if time.monotonic() - last < 3:
            st.info("Please wait a few seconds between live checks.")
        else:
            st.session_state["plus_live_clock"] = time.monotonic()
            try:
                with st.spinner("Asking NYC Open Data about this building…"):
                    st.session_state["plus_live"] = (building_id, cached_live(building_id, date.today().isoformat()))
            except services.ServiceError as exc:
                st.session_state.pop("plus_live", None)
                st.warning(f"Live records unavailable. {exc} The saved snapshot above is unaffected.")
    result = st.session_state.get("plus_live")
    if not result or result[0] != building_id:   # never show another building's records
        return
    records, violations, truncated = result[1]
    complaints = records.complaints
    wide = sum(item.scope == "Building-wide" for item in complaints)
    first, second, third = st.columns(3)
    first.metric(f"Complaints since {records.season_start.day} {records.season_start:%B %Y}", f"{len(complaints):,}")
    second.metric("Reported as building-wide", f"{wide:,}")
    third.metric("Most recent complaint", f"{complaints[0].received.day} {complaints[0].received:%b %Y}"
                 if complaints else "None on record")
    if complaints:
        st.dataframe(pd.DataFrame({
            "Received": [item.received.date() for item in complaints],
            "Problem": [item.problem for item in complaints],
            "Reported for": [item.scope for item in complaints],
            "Complaint status": [item.status for item in complaints],
        }), hide_index=True, height=min(38 * len(complaints) + 40, 280))
    else:
        st.info("NYC Open Data lists no heat or hot-water complaint for this building since 1 October. "
                "That is not proof that no problem occurred.")
    heat = [item for item in violations if item.heat_related]
    classes = {letter: sum(item.violation_class == letter for item in violations) for letter in "ABC"}
    st.markdown(f"**Open HPD violations, all types:** {len(violations):,} "
                f"(Class C, immediately hazardous: {classes['C']:,} · Class B, hazardous: {classes['B']:,} · "
                f"Class A: {classes['A']:,}). **Mentioning heat or hot water:** {len(heat):,}.")
    if heat:
        st.dataframe(pd.DataFrame({
            "Inspected": [item.inspected for item in heat], "Class": [item.violation_class for item in heat],
            "HPD description": [item.description[:220] for item in heat],
        }), hide_index=True, height=min(38 * len(heat) + 40, 240))
    if records.truncated or truncated:
        st.caption("Only the most recent 2,000 records were retrieved; totals may be higher.")
    st.caption("Source: NYC Open Data, HPD complaints and HPD violations. A violation is an inspector's finding; "
               "a complaint is a report that may not have been verified. Open violations can remain on record "
               "after a repair until the owner certifies the correction.")


def estimates_card(frame: pd.DataFrame, row: pd.Series, report: dict) -> None:
    backtest, threshold = report["backtest"], report["chronic_threshold"]
    with st.container(border=True, key="plus_estimates"):
        ui.section(f"Three estimates for the {report['deploy_season']} season", "risk", "estimates")
        any_column, chronic_column, count_column = st.columns(3, gap="medium")
        with any_column:
            st.metric("At least one recorded complaint", percent(row.PredictedRisk))
            st.caption("Original TenantShield model. Fixed before the season began.")
            st.write(rank_text(store.share_below(frame.PredictedRisk, row.PredictedRisk)))
            band = store.band_for(report["early_season_check"]["reliability"], row.PredictedRisk)
            if band:
                st.caption(f"Early check: of {band['n']:,} buildings with an estimate between {band_text(band, ' and ')}, "
                           f"{band['observed_rate']:.1%} already have a recorded complaint this season, "
                           "which runs to 31 May.")
        with chronic_column:
            st.metric(f"{threshold} or more recorded complaints", percent(row.ChronicRisk))
            st.caption("Companion model. A sign of repeated trouble rather than a single report.")
            st.write(rank_text(store.share_below(frame.ChronicRisk, row.ChronicRisk)))
            band = store.band_for(backtest["chronic_reliability"], row.ChronicRisk)
            if band:
                st.caption(f"Backtest: of {band['n']:,} buildings scored {band_text(band)} for "
                           f"{report['test_season']}, {band['observed_rate']:.1%} recorded {threshold} or more.")
        with count_column:
            expected = row.ExpectedComplaints
            st.metric("Expected recorded complaints", count_text(expected))
            st.caption("Companion model. An average, so most buildings land below it and a few far above.")
            rate = store.per_100_units(expected, row.Units)
            st.write(f"About {rate:,.0f} per 100 residential units." if rate is not None and expected >= .1
                     else "Fewer than one complaint expected.")
            band = store.count_band(backtest["count"]["bins"], expected)
            if band:
                st.caption(f"Backtest: buildings with a similar expected count averaged {band['mean_actual']:.1f} "
                           f"complaints in {report['test_season']}; half recorded {band['p50']:.0f} or fewer and "
                           f"one in ten recorded {band['p90']:.0f} or more.")
        ui.note("All three are building-level estimates of <strong>recorded HPD complaints</strong>. They are not "
                "apartment-level risks, verified heating failures or safety ratings, and they may be too high or "
                "too low. The companion models are separate from the original model and do not change its score.")


def peers_card(frame: pd.DataFrame, row: pd.Series, report: dict) -> None:
    with st.container(border=True, key="plus_peers"):
        ui.section("How this building compares", "building", "comparison")
        any_rows = store.comparison(frame, row, "PredictedRisk")
        chronic_rows = store.comparison(frame, row, "ChronicRisk")
        st.dataframe(pd.DataFrame({
            "Compared with": [item["group"] for item in any_rows],
            "Buildings": [item["buildings"] for item in any_rows],
            "Any-complaint estimate is higher than": [math.floor(item["share_below"] * 100) for item in any_rows],
            "Typical any-complaint estimate": [item["median"] * 100 for item in any_rows],
            f"{report['chronic_threshold']}+ complaint estimate is higher than": [math.floor(item["share_below"] * 100) for item in chronic_rows],
        }), hide_index=True, column_config={
            "Buildings": st.column_config.NumberColumn(format="localized"),
            "Any-complaint estimate is higher than": st.column_config.ProgressColumn(
                format="%.0f%% of group", min_value=0, max_value=100),
            "Typical any-complaint estimate": st.column_config.NumberColumn(format="%.1f%%", help="Group median."),
            f"{report['chronic_threshold']}+ complaint estimate is higher than": st.column_config.ProgressColumn(
                format="%.0f%% of group", min_value=0, max_value=100),
        })
        st.caption("Larger buildings have more apartments and more potential reporters, so the size comparison is "
                   "often the fairest one. Buildings tied with this one are not counted as lower.")


def history_card(row: pd.Series, report: dict) -> None:
    seasons = [c for c in store.season_columns(row.to_frame().T) if not pd.isna(row[c])]
    with st.container(border=True, key="plus_history"):
        ui.section("Recorded complaint history", "history", "history")
        if not seasons:
            st.info("No complete season is available for this building.")
            return
        last = seasons[-1]
        data = pd.DataFrame({"Season": [store.season_label(c) for c in seasons],
                             "Complaints": [int(row[c]) for c in seasons]})
        chart_column, facts = st.columns([3, 2], gap="medium")
        with chart_column:
            st.altair_chart(charts.bars(data, "Season", "Complaints", "Recorded complaints"), width="stretch")
            st.caption("Complete heating seasons, 1 October to 31 May. The current season is shown above, not here.")
        with facts:
            rate = store.per_100_units(row[last], row.Units)
            st.metric(f"Per 100 units, {store.season_label(last)}", "Unavailable" if rate is None else f"{rate:,.0f}",
                      help="Complaints divided by registered residential units. Unavailable when the unit count is missing.")
            left, right = st.columns(2)
            left.metric("Different apartments", f"{int(row.ApartmentsLastSeason):,}",
                        help=f"Apartments with an apartment-level complaint in {store.season_label(last)}.")
            right.metric("Building-wide complaints", f"{int(row.BuildingWideLastSeason):,}",
                         help=f"Complaints reported for the whole building in {store.season_label(last)}.")
            st.metric("June–September complaints", f"{int(row.OffSeasonBefore):,}",
                      help="Recorded in the summer before this season, when heat is not required. Usually hot water.")
        with st.expander("View as a table"):
            st.dataframe(data, hide_index=True)
        ui.note("Counts are unique HPD complaints in the public extract. One persistent tenant can file many "
                "complaints, and other tenants may file none, so read the count together with the number of "
                "different apartments. Zero recorded complaints is not proof of zero problems.")


def nearby_card(frame: pd.DataFrame, row: pd.Series) -> None:
    with st.container(border=True, key="plus_nearby"):
        ui.section("Nearby buildings", "location", "nearby")
        if pd.isna(row.Latitude):
            st.info("No tax-lot location is available for this building, so nearby buildings cannot be listed.")
            return
        radius = st.segmented_control("Distance", RADII, default=RADII[1], format_func=lambda m: f"{m} m",
                                      key="plus_radius") or RADII[1]
        near = store.nearby(frame, row, radius)
        if near.empty:
            st.info(f"No other scored building lies within {radius} m.")
            return
        lower = math.floor(store.share_below(near.PredictedRisk, row.PredictedRisk) * 100)
        st.write(f"**{len(near):,}** other scored buildings within {radius} m. This building's any-complaint "
                 f"estimate is higher than **{lower}%** of them, and **{int(near.SeasonToDate.gt(0).sum()):,}** "
                 "of them already have a recorded complaint this season.")
        table = near.assign(Estimate=near.PredictedRisk * 100, Chronic=near.ChronicRisk * 100)
        st.dataframe(table[["FullAddress", "DistanceM", "Units", "Estimate", "Chronic", "SeasonToDate"]],
                     hide_index=True, height=250, column_config={
            "FullAddress": "Address", "DistanceM": st.column_config.NumberColumn("Distance", format="%d m"),
            "Units": st.column_config.NumberColumn("Registered units", format="%d"),
            "Estimate": st.column_config.NumberColumn("Any complaint", format="%.1f%%"),
            "Chronic": st.column_config.NumberColumn("5+ complaints", format="%.1f%%"),
            "SeasonToDate": st.column_config.NumberColumn("This season so far", format="%d"),
        })
        st.caption("Distances are between tax-lot points from NYC PLUTO, so they are approximate. "
                   "Sorted nearest first; click a column heading to sort.")
        if st.toggle("Show these buildings on a map", key=f"plus_map_{row.BuildingID}",
                     help="Loads map tiles from CARTO in your browser. Nothing is requested until you switch this on."):
            st.pydeck_chart(nearby_map(near, row), height=420)
            st.caption("Darker dots have a higher any-complaint estimate; the orange dot is this building. "
                       "Basemap © CARTO, © OpenStreetMap contributors. Locations are tax-lot points, not entrances.")


def nearby_map(near: pd.DataFrame, row: pd.Series) -> pdk.Deck:
    light, dark = (198, 219, 245), (16, 52, 110)     # one hue, light to dark, on a square-root scale
    weight = near.PredictedRisk.clip(0, 1) ** .5
    points = pd.DataFrame({
        "lon": near.Longitude, "lat": near.Latitude, "address": near.FullAddress,
        "estimate": near.PredictedRisk.map(percent),
        "color": [[round(a + (b - a) * w) for a, b in zip(light, dark)] + [230] for w in weight],
    })
    here = pd.DataFrame({"lon": [row.Longitude], "lat": [row.Latitude], "address": [row.FullAddress],
                         "estimate": [percent(row.PredictedRisk)]})
    layers = [
        pdk.Layer("ScatterplotLayer", points, get_position="[lon, lat]", get_fill_color="color", get_radius=7,
                  radius_min_pixels=4, stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1,
                  pickable=True),
        pdk.Layer("ScatterplotLayer", here, get_position="[lon, lat]", get_fill_color=[235, 104, 52], get_radius=11,
                  radius_min_pixels=8, stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2,
                  pickable=True),
    ]
    view = pdk.ViewState(latitude=float(row.Latitude), longitude=float(row.Longitude), zoom=16)
    return pdk.Deck(layers=layers, initial_view_state=view, map_style="light",
                    tooltip={"text": "{address}\nAny-complaint estimate: {estimate}"})


def questions_card(row: pd.Series, report: dict) -> None:
    questions = viewing_questions(row, report["chronic_threshold"], ui.pretty_date(report["data_through"]))
    with st.container(border=True, key="plus_questions"):
        ui.section("Questions for your viewing", "method", "questions")
        for index, question in enumerate(questions):
            st.checkbox(question, key=f"question_{row.BuildingID}_{index}")
        with st.expander("Your heat and hot-water rights in New York City"):
            st.markdown("\n".join(f"- {rule}" for rule in HEAT_RULES))
            st.markdown(f"[NYC HPD: heat and hot water information]({HEAT_RULES_URL})")
        st.download_button("Download this summary", text_summary(row, report, questions),
                           file_name=f"tenantshield-{row.BuildingID}.md", mime="text/markdown",
                           key=f"download_{row.BuildingID}", on_click="ignore")


@st.fragment
def street_card(row: pd.Series) -> None:
    with st.container(border=True, key="plus_street"):
        ui.section("Location & street context", "street", "location")
        if pd.isna(row.Latitude):
            st.info("No tax-lot location is available. Use the main TenantShield app to geocode this address on demand.")
            return
        location = services.Location(float(row.Latitude), float(row.Longitude), row.FullAddress)
        _, full = map_urls(location)
        st.markdown(f"[Open this location on OpenStreetMap]({full}) · approximate tax-lot point from NYC PLUTO")
        key = ui.setting("GOOGLE_MAPS_API_KEY")
        if not key:
            st.caption("Street View unavailable: optional Google API access is not configured.")
            return
        if not st.button("Load nearby Street View", key=f"plus_street_{row.BuildingID}"):
            st.caption("One metadata check and at most one image per click. Imagery is supplied by Google Maps "
                       "and may show a different façade.")
            return
        last = st.session_state.get("street_last_request", float("-inf"))
        if time.monotonic() - last < 10:
            st.info("Please wait 10 seconds between image requests, then load again.")
            return
        st.session_state["street_last_request"] = time.monotonic()
        try:
            with st.spinner("Checking imagery availability…"):
                image = services.street_view(key, location)
        except services.ServiceError as exc:
            message = str(exc)
            st.warning(message if message.startswith("Street View unavailable") else f"Street View unavailable. {message}")
            return
        if image is None:
            st.info("Street View unavailable: no suitable outdoor imagery was found nearby.")
            return
        try:
            # Bytes only, never a key-bearing URL, and no caching of Google imagery.
            st.image(image.content, caption=f"Google Maps · {image.date} · {image.copyright}", width="stretch")
        except (OSError, SyntaxError, ValueError):
            st.warning("Street View unavailable: the returned image could not be displayed.")


def shortlist_button(building_id: str) -> None:
    chosen = ui.shortlist()
    if building_id in chosen:
        if st.button("Remove from shortlist", key=f"shortlist_remove_{building_id}"):
            chosen.remove(building_id)
            st.rerun()
    elif len(chosen) >= ui.MAX_SHORTLIST:
        st.caption(f"Shortlist is full ({ui.MAX_SHORTLIST} buildings). Remove one on the Compare Shortlist page.")
    elif st.button("Add to shortlist", key=f"shortlist_add_{building_id}",
                   help="Compare up to four buildings side by side."):
        chosen.append(building_id)
        st.rerun()


def profile(frame: pd.DataFrame, row: pd.Series, report: dict) -> None:
    st.header(row.FullAddress or "Address unavailable")
    units = "Units unavailable" if pd.isna(row.Units) else f"{int(row.Units):,} residential units"
    ui.badges([f"BIN {row.BIN or 'unavailable'}", f"Building ID {row.BuildingID}",
               f"Brooklyn, NY {row.Zip}" if store.valid_zip(row.get("Zip")) else "Brooklyn, NY", units, f"{report['deploy_season']} heating season"])
    shortlist_button(row.BuildingID)
    if not store.has_plus(row):
        st.metric("At least one recorded complaint", percent(row.PredictedRisk))
        st.warning("Plus estimates are not available for this building. The original estimate is shown above.")
        return
    season_card(row, report)
    estimates_card(frame, row, report)
    peers_card(frame, row, report)
    history_card(row, report)
    nearby_card(frame, row)
    questions_card(row, report)
    street_card(row)


# ----------------------------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------------------------

def submit_search() -> None:
    st.session_state.plus_query = st.session_state.plus_input.strip()
    st.session_state.pop("plus_open", None)


def change_mode() -> None:
    st.session_state.plus_input = ""
    submit_search()


def open_sample() -> None:
    st.session_state.plus_open = SAMPLE_ID
    st.session_state.plus_query = st.session_state.plus_input = ""


def main() -> None:
    ui.shell("Building Check")
    frame, report = ui.load()
    st.title("Check a Brooklyn building's heat record before you rent.")
    st.markdown("TenantShield Plus adds this season's recorded complaints, an estimate of repeated complaints, "
                "comparisons with nearby and similar buildings, and questions to take to your viewing.")
    state = st.session_state
    state.setdefault("plus_input", state.get("plus_query", ""))
    with st.container(border=True, key="search_card"):
        ui.section("Find a building", "search", "search")
        mode = st.radio("Search by", ["Address", "BIN"], horizontal=True, key="plus_mode", on_change=change_mode)
        with st.form("plus_lookup", border=False):
            st.text_input("Brooklyn address" if mode == "Address" else "Building Identification Number (BIN)",
                          placeholder="Enter a Brooklyn address" if mode == "Address" else "Enter the full 7-digit BIN",
                          max_chars=160, key="plus_input")
            search_action, sample_action = st.columns(2, gap="small")
            search_action.form_submit_button("Search", type="primary", width="stretch", on_click=submit_search)
            sample_action.form_submit_button("Try a sample building", width="stretch", on_click=open_sample,
                                             disabled=SAMPLE_ID not in frame.index)
        st.caption(f"Searches run on this server's saved data. Complaint records through "
                   f"{ui.pretty_date(report['data_through'])}.")
    selected = state.get("plus_open") if state.get("plus_open") in frame.index else None
    query = state.get("plus_query", "")
    if selected is None and query:
        matches = search_buildings(frame, query, mode)
        if matches.empty:
            st.info("No matching building in the scored dataset. Try a shorter street address or check the full BIN. "
                    "This dataset does not cover every Brooklyn building.")
        else:
            if mode == "BIN" and query.strip() == "3000000":
                st.warning("This is a placeholder BIN shared by several records. Choose the correct building below.")
            st.caption(f"{len(matches):,} matching building{'s' if len(matches) != 1 else ''}")
            if len(matches) > 200:
                st.info("Showing the first 200 matches. Add a house number or more of the street name to narrow the search.")
            options = matches.index[:200].tolist()
            selected = options[0] if len(options) == 1 else st.selectbox(
                "Choose a building", options, index=None, placeholder="Select the address and building ID…",
                key=f"plus_choice_{mode}_{query}", format_func=lambda bid: ui.building_label(frame, bid))
    if selected is not None:
        profile(frame, frame.loc[selected], report)
    st.divider()
    st.page_link("pages/Evidence.py", label="How these estimates were made and tested", icon=":material/menu_book:")
    st.caption("TenantShield is an educational prototype. Estimates describe recorded HPD complaints for a building; "
               "they do not guarantee the condition of any building or apartment.")


if __name__ == "__main__":
    main()
