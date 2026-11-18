"""Side-by-side comparison of up to four shortlisted buildings. Reads precomputed values only."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from tsplus import store, ui  # noqa: E402
from tenantshield.data import search_buildings  # noqa: E402


def value_or_dash(value: object, pattern: str = "{:,.0f}") -> str:
    return "Unavailable" if value is None or pd.isna(value) else pattern.format(value)


ui.shell("Compare Shortlist")
frame, report = ui.load()
threshold, season = report["chronic_threshold"], report["deploy_season"]
chosen = [bid for bid in ui.shortlist() if bid in frame.index]
st.session_state["shortlist"] = chosen

st.title("Compare your shortlist")
st.write(f"Put up to {ui.MAX_SHORTLIST} buildings side by side. Add them here or from the Building Check page.")

with st.container(border=True, key="plus_add"):
    ui.section("Add a building", "search", "add")
    with st.form("shortlist_search", border=False):
        text = st.text_input("Brooklyn address", placeholder="Enter a Brooklyn address", max_chars=160, key="shortlist_input")
        st.form_submit_button("Find", type="primary")
    if text.strip():
        matches = search_buildings(frame, text)
        if matches.empty:
            st.info("No matching building in the scored dataset.")
        else:
            options = matches.index[:200].tolist()
            pick = st.selectbox("Choose a building", options, index=0 if len(options) == 1 else None,
                                placeholder="Select the address and building ID…", key=f"shortlist_pick_{text}",
                                format_func=lambda bid: ui.building_label(frame, bid))
            full = len(chosen) >= ui.MAX_SHORTLIST
            if pick and st.button("Add to shortlist", disabled=full or pick in chosen, key="shortlist_add"):
                chosen.append(pick)
                st.rerun()
            if full:
                st.caption("The shortlist is full. Remove a building below to add another.")

if not chosen:
    st.info("Your shortlist is empty. Search above, or open a building and choose “Add to shortlist”.")
    st.stop()

rows = frame.loc[chosen]
last = store.season_columns(frame)[-1]
with st.container(border=True, key="plus_compare"):
    ui.section("Side by side", "building", "side-by-side")
    table = pd.DataFrame({
        "Measure": [
            f"Chance of at least one recorded complaint, {season}",
            f"Chance of {threshold} or more recorded complaints, {season}",
            f"Expected recorded complaints, {season}",
            "Recorded complaints since 1 October",
            "Chance of at least one more complaint by 31 May",
            f"Recorded complaints, {store.season_label(last)} season",
            f"Complaints per 100 units, {store.season_label(last)}",
            f"Different apartments complaining, {store.season_label(last)}",
            f"Building-wide complaints, {store.season_label(last)}",
            "Residential units", "Stories", "Construction year",
        ],
    })
    for building_id, row in rows.iterrows():
        rate = store.per_100_units(row[last], row.Units)
        plus = store.has_plus(row)
        table[row.FullAddress or f"Building {building_id}"] = [
            f"{row.PredictedRisk:.1%}",
            f"{row.ChronicRisk:.1%}" if plus else "Unavailable",
            f"{row.ExpectedComplaints:,.1f}" if plus else "Unavailable",
            value_or_dash(row.get("SeasonToDate")),
            f"{row.RestOfSeasonRisk:.1%}" if plus else "Unavailable",
            value_or_dash(row.get(last)),
            value_or_dash(rate),
            value_or_dash(row.get("ApartmentsLastSeason")),
            value_or_dash(row.get("BuildingWideLastSeason")),
            value_or_dash(row.get("Units")),
            value_or_dash(row.LegalStories if row.LegalStories and row.LegalStories > 0 else None),
            value_or_dash(row.get("Construction Year"), "{:.0f}"),
        ]
    st.dataframe(table, hide_index=True, height=38 * len(table) + 40)
    st.caption(f"Complaint records through {ui.pretty_date(report['data_through'])}. Two buildings at the same address are "
               "separate HPD records and appear as separate columns.")
    ui.note("Larger buildings have more potential reporters, so compare the per-100-units row as well as the totals. "
            "These are estimates of recorded complaints, not rankings of safety, and small differences between "
            "buildings are not meaningful.")

with st.container(border=True, key="plus_manage"):
    ui.section("Manage shortlist", "method", "manage")
    for building_id in list(chosen):
        name, action = st.columns([4, 1])
        name.write(ui.building_label(frame, building_id))
        if action.button("Remove", key=f"remove_{building_id}"):
            chosen.remove(building_id)
            st.rerun()
    st.caption("The shortlist lives in this browser session only and is cleared when the session ends.")
