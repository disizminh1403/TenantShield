"""ZIP-code context: how complaint records and estimates vary across the scored Brooklyn cohort."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from tsplus import charts, store, ui  # noqa: E402

ui.shell("Area Explorer")
frame, report = ui.load()
season, threshold = report["deploy_season"], report["chronic_threshold"]
last = store.season_columns(frame)[-1]
last_label = store.season_label(last)
summary = store.area_summary(frame)

st.title("Explore Brooklyn by ZIP code")
st.write("Recorded heat and hot-water complaints and the precomputed estimates, summarised by ZIP code. "
         "Use it to see how a neighbourhood compares before you look at single buildings.")

with st.container(border=True, key="plus_zip_overview"):
    ui.section(f"Share of buildings with a recorded complaint, {last_label}", "location", "overview")
    chart_data = summary.reset_index().rename(columns={"ComplaintLastSeasonShare": "Share"})
    chart_data["ZIP"] = chart_data.Zip
    st.altair_chart(charts.bars(chart_data, "ZIP", "Share", "Buildings with a complaint", percent=True,
                                horizontal=True, height=18 * len(chart_data) + 40), width="stretch")
    st.caption(f"Each bar is one ZIP code, highest first. Complete {last_label} heating season, scored buildings only.")
    with st.expander("View all ZIP codes as a table"):
        display = summary.assign(**{column: summary[column] * 100 for column in (
            "ComplaintThisSeasonShare", "ComplaintLastSeasonShare", "MedianEstimate", "MeanEstimate", "MeanChronicRisk")})
        st.dataframe(display, column_config={
            "Zip": "ZIP", "Buildings": st.column_config.NumberColumn(format="localized"),
            "ComplaintThisSeasonShare": st.column_config.NumberColumn("With a complaint this season so far", format="%.1f%%"),
            "ComplaintLastSeasonShare": st.column_config.NumberColumn(f"With a complaint in {last_label}", format="%.1f%%"),
            "ComplaintsPer100Units": st.column_config.NumberColumn(f"Complaints per 100 units, {last_label}", format="%.1f"),
            "MedianEstimate": st.column_config.NumberColumn(f"Median any-complaint estimate, {season}", format="%.1f%%"),
            "MeanEstimate": st.column_config.NumberColumn(f"Average any-complaint estimate, {season}", format="%.1f%%"),
            "MeanChronicRisk": st.column_config.NumberColumn(f"Average {threshold}+ complaint estimate", format="%.1f%%"),
        })
    ui.note("ZIP codes differ in building size, tenure and how readily tenants report problems. A higher share "
            "describes recorded complaints in that area; it is not a rating of the neighbourhood or of any building in it.")

with st.container(border=True, key="plus_zip_detail"):
    ui.section("Buildings in one ZIP code", "building", "zip-detail")
    zips = sorted(summary.index)
    left, middle, right = st.columns([1, 1, 2])
    zip_code = left.selectbox("ZIP code", zips, key="area_zip")
    minimum = middle.number_input("Minimum residential units", min_value=0, max_value=500, value=6, step=1, key="area_units",
                                  help="Small buildings rarely record complaints; raise this to compare apartment buildings.")
    order = right.selectbox("Sort by", ["Any-complaint estimate", f"{threshold}+ complaint estimate",
                                        "Complaints this season so far", f"Complaints in {last_label}"], key="area_sort")
    area = frame[frame.Zip.eq(zip_code)]
    listed = area[area.Units.fillna(0).ge(minimum)] if minimum else area
    totals = summary.loc[zip_code]
    one, two, three, four = st.columns(4)
    one.metric("Scored buildings", f"{len(area):,}")
    two.metric(f"With a complaint in {last_label}", f"{totals.ComplaintLastSeasonShare:.1%}")
    three.metric("With a complaint this season so far", f"{totals.ComplaintThisSeasonShare:.1%}")
    four.metric(f"Complaints per 100 units, {last_label}",
                "Unavailable" if pd.isna(totals.ComplaintsPer100Units) else f"{totals.ComplaintsPer100Units:,.1f}")
    column = {"Any-complaint estimate": "PredictedRisk", f"{threshold}+ complaint estimate": "ChronicRisk",
              "Complaints this season so far": "SeasonToDate", f"Complaints in {last_label}": last}[order]
    listed = listed.sort_values([column, "FullAddress"], ascending=[False, True], kind="stable")
    st.caption(f"{len(listed):,} buildings with at least {minimum} residential units. Showing the first 500.")
    view = listed.head(500).assign(Estimate=lambda d: d.PredictedRisk * 100, Chronic=lambda d: d.ChronicRisk * 100)
    st.dataframe(view[["FullAddress", "Units", "Estimate", "Chronic", "SeasonToDate", last]], hide_index=True, column_config={
        "FullAddress": "Address", "Units": st.column_config.NumberColumn("Units", format="%d"),
        "Estimate": st.column_config.NumberColumn("Any complaint", format="%.1f%%"),
        "Chronic": st.column_config.NumberColumn(f"{threshold}+ complaints", format="%.1f%%"),
        "SeasonToDate": st.column_config.NumberColumn("This season so far", format="%d"),
        last: st.column_config.NumberColumn(last_label, format="%d"),
    })
    st.caption(f"Complaint records through {ui.pretty_date(report['data_through'])}. To see a full profile, search the address on "
               "the Building Check page.")
    st.page_link("app.py", label="Open Building Check", icon=":material/apartment:")
