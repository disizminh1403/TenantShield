"""Evidence and method for the companion estimates. Every figure is read from plus/data/plus_report.json."""

from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from tsplus import charts, ui  # noqa: E402

FEATURES = {
    "c1": "Complaints last season", "c2": "Complaints two seasons ago", "c3": "Complaints three seasons ago",
    "apts1": "Different apartments complaining last season", "bw1": "Building-wide complaints last season",
    "months1": "Months with a complaint last season", "off1": "June–September complaints before the season",
    "units": "Residential units", "stories": "Stories", "year": "Construction year",
    "zip_rate1": "Share of the ZIP's buildings with a complaint last season",
    "todate": "Complaints so far this season", "todate_apts": "Different apartments so far this season",
    "log_units": "Residential units (log)", "missing_units": "Unit count missing",
    "has1": "Prior-season history available", "has2": "Two-seasons-prior history available",
}
METRIC_COLUMNS = {
    "roc_auc": st.column_config.NumberColumn("ROC-AUC", format="%.3f", help="Ranking quality across all thresholds. Higher is better."),
    "pr_auc": st.column_config.NumberColumn("PR-AUC", format="%.3f", help="Precision–recall trade-off. Higher is better; depends on how common the outcome is."),
    "brier": st.column_config.NumberColumn("Brier score", format="%.4f", help="Squared error of the probabilities. Lower is better."),
    "top_decile_recall": st.column_config.NumberColumn("Top-10% recall", format="%.1f%%", help="Share of all positive buildings found in the highest-scored 10%."),
    "top_decile_precision": st.column_config.NumberColumn("Top-10% precision", format="%.1f%%", help="Share of the highest-scored 10% that were positive."),
}


def subheading(text: str) -> None:
    st.markdown(f"**{text}**")


def metrics_table(results: list[dict], first_columns: list[str]) -> None:
    table = pd.DataFrame(results)
    for column in ("top_decile_recall", "top_decile_precision"):
        table[column] *= 100
    st.dataframe(table[[*first_columns, *METRIC_COLUMNS]], hide_index=True, column_config={
        "features": "Inputs", "model": "Model", **METRIC_COLUMNS})


def reliability_chart(bands: list[dict], observed_label: str) -> None:
    data = pd.DataFrame({"Band": [f"{b['low']:.0%}–{b['high']:.0%}" for b in bands],
                         "predicted": [b["mean_score"] for b in bands], "observed": [b["observed_rate"] for b in bands],
                         "Buildings": [b["n"] for b in bands]})
    st.altair_chart(charts.paired_bars(data, "Band", ("predicted", "Average estimate"), ("observed", observed_label),
                                       "Share of buildings"), width="stretch")
    with st.expander("View as a table"):
        st.dataframe(data.assign(predicted=data.predicted * 100, observed=data.observed * 100), hide_index=True, column_config={
            "Band": "Estimate band", "predicted": st.column_config.NumberColumn("Average estimate", format="%.1f%%"),
            "observed": st.column_config.NumberColumn(observed_label, format="%.1f%%"),
            "Buildings": st.column_config.NumberColumn(format="localized")})


ui.shell("Evidence & Method")
frame, report = ui.load()
backtest, threshold = report["backtest"], report["chronic_threshold"]
test, deploy, train = report["test_season"], report["deploy_season"], " and ".join(report["train_seasons"])
gb = lambda rows, inputs: next(r for r in rows if r["model"] == "Gradient boosting" and r["features"] == inputs)  # noqa: E731

st.title("Evidence & method")
st.write("What the companion estimates predict, how they were tested on a season the models never saw, "
         "and where they fall short.")

with st.container(border=True, key="plus_ev_what"):
    ui.section("What TenantShield Plus adds", "shield", "what")
    st.markdown(f"""
The original TenantShield score answers one question: will this building record **at least one** heat or hot-water
complaint in {deploy}? About one building in ten does, so that question says little about how bad a winter might be.
Three companion estimates, built offline from the same public HPD records, add detail:

- **{threshold} or more recorded complaints**: a sign of repeated trouble rather than a single report.
- **Expected number of recorded complaints** for the season.
- **At least one more complaint by 31 May**, updated with complaints already recorded since 1 October.

The original `PredictedRisk` is displayed unchanged. Nothing is trained inside this web app.
    """)
    ui.note("Every outcome here is a <strong>recorded HPD complaint</strong>. It is not a verified heating failure, "
            "an apartment-level probability or a safety rating.")

with st.container(border=True, key="plus_ev_chronic"):
    chronic = gb(backtest["chronic"], "Expanded history")
    rule = backtest["chronic_rule_same_as_last_season"]
    ui.section(f"Backtest: {threshold} or more complaints", "risk", "chronic")
    st.caption(f"TRAINED ON {train.upper()} · TESTED ONCE ON {test} · {chronic['n']:,} BUILDINGS · "
               f"{chronic['positives']:,} WITH {threshold} OR MORE COMPLAINTS ({chronic['prevalence']:.1%})")
    one, two, three, four = st.columns(4)
    one.metric("ROC-AUC", f"{chronic['roc_auc']:.3f}")
    two.metric("PR-AUC", f"{chronic['pr_auc']:.3f}")
    three.metric("Top-10% recall", f"{chronic['top_decile_recall']:.1%}",
                 help=f"Share of all buildings with {threshold}+ complaints that were in the highest-scored 10%.")
    four.metric("Top-10% precision", f"{chronic['top_decile_precision']:.1%}")
    st.markdown(f"The highest-scored 10% of buildings contained **{chronic['top_decile_recall']:.0%}** of all buildings "
                f"that went on to record {threshold} or more complaints. A simple rule, “flag every building that had "
                f"{threshold} or more last season”, flags {rule['flagged']:,} buildings and finds {rule['recall']:.0%} "
                f"of them ({rule['precision']:.0%} of its flags were right).")
    subheading("Did the probabilities match what happened?")
    reliability_chart(backtest["chronic_reliability"], f"Recorded {threshold}+ in {test}")
    st.caption(f"Buildings are grouped by their estimate. In a well-calibrated model the two bars in each group are "
               f"level. Here the observed bar is slightly higher in most groups: {test} had more complaints than the "
               "training seasons, so the estimates ran a little low.")
    subheading("Model comparison")
    metrics_table(backtest["chronic"], ["model"])
    subheading("Which inputs mattered")
    importance = pd.DataFrame(backtest["chronic_importance"])
    importance["Input"] = importance.feature.map(FEATURES)
    importance["drop"] = importance.pr_auc_drop.clip(lower=0)
    st.altair_chart(charts.bars(importance, "Input", "drop", "Drop in PR-AUC when shuffled", horizontal=True,
                                height=26 * len(importance) + 40, decimals=3), width="stretch")
    st.caption("Each input is shuffled in the held-out season and the loss in PR-AUC recorded. Larger means the model "
               "leans on it more. This describes the model, not what causes complaints.")

with st.container(border=True, key="plus_ev_any"):
    ui.section("Random forest, gradient boosting and logistic regression", "method", "comparison")
    st.caption(f"OUTCOME: AT LEAST ONE RECORDED COMPLAINT · TRAINED ON {train.upper()} · TESTED ON {test}")
    metrics_table(backtest["any_complaint"], ["features", "model"])
    six, rich = gb(backtest["any_complaint"], "Original six inputs"), gb(backtest["any_complaint"], "Expanded history")
    replica = report["replication_check"]
    st.markdown(f"""
- **The three model families perform similarly** on the same inputs; the choice of inputs matters more than the choice of model.
- **More history helps.** Adding a third season, apartment and building-wide detail, summer complaints and building
  characteristics lifts gradient-boosting PR-AUC from {six['pr_auc']:.3f} to {rich['pr_auc']:.3f}.
- **The data reconstruction agrees with the original model.** A Python gradient-boosting model refit here on the
  original six inputs correlates {replica['pearson']:.3f} with the R/XGBoost `PredictedRisk` in the app data
  (average absolute difference {replica['mean_abs_difference']:.1%}).
    """)
    st.caption("These rows are a Python re-implementation on a panel rebuilt from public data. They are not the "
               "original R results, which are reported on the main app's methodology page.")

with st.container(border=True, key="plus_ev_rest"):
    before, after = backtest["rest_of_season"]
    ui.section("Backtest: updating the estimate during the season", "history", "rest")
    st.markdown(f"Outcome: at least one more complaint between the same calendar cut-off and 31 May, tested on {test}. "
                f"Adding the complaints already recorded since 1 October raises PR-AUC from **{before['pr_auc']:.3f}** "
                f"to **{after['pr_auc']:.3f}** and top-10% recall from {before['top_decile_recall']:.1%} to "
                f"{after['top_decile_recall']:.1%}.")
    reliability_chart(backtest["rest_reliability"], f"Recorded one more in {test}")
    st.caption("How mild or cold the autumn has been differs by year, so an early count carries a somewhat different "
               "meaning each season. The model sees three seasons of this pattern.")

with st.container(border=True, key="plus_ev_count"):
    count = backtest["count"]
    ui.section("Backtest: expected number of complaints", "risk", "count")
    one, two, three = st.columns(3)
    one.metric("Average error per building", f"{count['mae_model']:.3f}",
               help="Mean absolute error in complaints per building.")
    two.metric("Same-as-last-season rule", f"{count['mae_same_as_last_season']:.3f}",
               help="Mean absolute error when predicting that each building repeats last season's count.")
    three.metric("Complaints in the top 10%", f"{count['top_decile_share_of_complaints']:.0%}",
                 help="Share of all recorded complaints that came from the 10% of buildings with the highest expected count.")
    st.markdown(f"The model expected **{count['total_expected']:,.0f}** complaints across the cohort in {test}; "
                f"**{count['total_actual']:,}** were recorded. That season was unusually heavy, and a model trained on "
                "earlier seasons cannot foresee a cold winter. Treat expected counts as a typical-season figure.")
    bins = pd.DataFrame(count["bins"])
    bins["Band"] = [f"{low:g}–{high:g}" if high is not None and not pd.isna(high) else f"{low:g}+"
                    for low, high in zip(bins.low, bins.high)]
    st.dataframe(bins[["Band", "n", "mean_expected", "mean_actual", "p50", "p90"]], hide_index=True, column_config={
        "Band": "Expected complaints", "n": st.column_config.NumberColumn("Buildings", format="localized"),
        "mean_expected": st.column_config.NumberColumn("Average expected", format="%.2f"),
        "mean_actual": st.column_config.NumberColumn(f"Average recorded, {test}", format="%.2f"),
        "p50": st.column_config.NumberColumn("Half recorded this or fewer", format="%.0f"),
        "p90": st.column_config.NumberColumn("One in ten recorded this or more", format="%.0f")})
    st.caption("Counts are very skewed, so this model fits log(1 + complaints) and rescales to the training total. "
               "A Poisson boosting objective was tried first and diverged on the largest buildings.")

with st.container(border=True, key="plus_ev_early"):
    early = report["early_season_check"]
    ui.section(f"Early check of the original score, {deploy}", "shield", "early")
    st.markdown(f"The original score was fixed before {deploy} began. From 1 October through "
                f"{ui.pretty_date(report['data_through'])}, **{early['positives']:,}** of {early['n']:,} scored buildings "
                f"({early['prevalence']:.1%}) have already recorded a complaint. The highest-scored 10% of buildings "
                f"contain **{early['top_decile_recall']:.0%}** of them (ROC-AUC {early['roc_auc']:.3f}).")
    reliability_chart(early["reliability"], "Already recorded a complaint")
    elapsed = (date.fromisoformat(report["data_through"]) - date(int(deploy[:4]), 10, 1)).days + 1
    st.caption("The observed bars are expected to sit far below the estimates: the estimate covers the whole season "
               f"to 31 May, and about {elapsed / 243:.0%} of it had passed. What this shows is ranking: buildings with "
               "higher estimates are recording complaints sooner. It is not a calibration test.")

with st.container(border=True, key="plus_ev_data"):
    ui.section("Data, summary statistics and a consistency check", "building", "data")
    seasons = pd.DataFrame(report["seasons"])
    subheading("Three seasons of the rebuilt panel")
    st.dataframe(seasons.assign(any_rate=seasons.any_rate * 100, chronic_rate=seasons.chronic_rate * 100,
                                share=seasons.share_of_complaints_from_chronic * 100)
                 [["season", "buildings", "complaints", "any_rate", "chronic_rate", "share"]], hide_index=True, column_config={
        "season": "Season", "buildings": st.column_config.NumberColumn("Eligible buildings", format="localized"),
        "complaints": st.column_config.NumberColumn("Recorded complaints", format="localized"),
        "any_rate": st.column_config.NumberColumn("With at least one", format="%.1f%%"),
        "chronic_rate": st.column_config.NumberColumn(f"With {threshold} or more", format="%.1f%%"),
        "share": st.column_config.NumberColumn(f"Complaints from buildings with {threshold}+", format="%.0f%%")})
    latest = report["seasons"][-1]
    persistence = report["persistence_2025"]
    st.markdown(f"""
- **Complaints are concentrated.** In {latest['season']}, {latest['chronic_rate']:.1%} of buildings recorded
  {threshold} or more complaints and accounted for {latest['share_of_complaints_from_chronic']:.0%} of all complaints.
- **Trouble persists.** {persistence['any_given_any_last_season']:.0%} of buildings with a complaint the season before
  had one again, against {persistence['any_given_none_last_season']:.1%} of buildings without. Among buildings with
  {threshold}+ the season before, {persistence['chronic_given_chronic_last_season']:.0%} reached {threshold}+ again.
    """)
    left, right = st.columns(2, gap="medium")
    with left:
        subheading(f"Complaint rate by building size, {test}")
        size = pd.DataFrame(report["rates_2025"]["by_units"])
        size["Units"] = size.group
        st.altair_chart(charts.bars(size, "Units", "any_rate", "Buildings with a complaint", percent=True), width="stretch")
        st.caption("Residential units per building. Larger buildings have more potential reporters.")
    with right:
        subheading("When complaints arrive")
        monthly = pd.DataFrame(report["monthly_share"])
        monthly["Month"] = monthly.month
        st.altair_chart(charts.bars(monthly, "Month", "share", "Share of season's complaints", percent=True), width="stretch")
        st.caption("Share of heating-season complaints by month, 2021–22 through 2025–26 combined.")
    subheading("Does the rebuilt history match the app data?")
    check = pd.DataFrame([{"Season": season, "Column in app CSV": item["csv_column"],
                           "oct_may": item["oct_to_may"]["exact_match_share"] * 100,
                           "oct_sep": item["oct_to_sep"]["exact_match_share"] * 100}
                          for season, item in report["history_check"].items()])
    st.dataframe(check, hide_index=True, column_config={
        "oct_may": st.column_config.NumberColumn("Buildings matching a 1 Oct–31 May count", format="%.2f%%"),
        "oct_sep": st.column_config.NumberColumn("Buildings matching a 1 Oct–30 Sep count", format="%.2f%%")})
    st.warning("The two history columns in the app data appear to cover different windows. The 2025–26 column matches "
               "a 1 October–31 May count, while the 2024–25 column matches a 1 October–30 September count, so it "
               "includes summer complaints. The Plus pages count every season from 1 October to 31 May and show "
               "June–September separately, so a 2024–25 figure here can be lower than on the main app.")

with st.container(border=True, key="plus_ev_limits"):
    ui.section("Limitations and responsible use", "shield", "limits")
    st.markdown(f"""
- **Complaints are reports.** They depend on tenants knowing about 311 and choosing to call. Fewer reports do not prove fewer problems.
- **One apartment can file many complaints.** Read counts together with the number of different apartments.
- **Size drives volume.** Large buildings pass {threshold} complaints far more easily than small ones; the per-100-units figures and the same-size comparison correct for some of this.
- **Seasons differ.** A colder winter raises complaints everywhere. All three backtests ran slightly low for {test} for this reason.
- **Today's building list is applied to past seasons.** Buildings that left the registry are missing, and construction year is only a proxy for when a building was occupied.
- **Locations are tax-lot points** from NYC PLUTO, joined by block and lot. They are approximate and are not entrances.
- **Separate models, separate claims.** The companion estimates were built in Python with scikit-learn gradient boosting; they are not outputs of the original R/XGBoost model and have not been reviewed as part of it.
- **Not a safety rating.** Use these figures alongside a viewing, current HPD records and conversations with tenants.
    """)
    st.caption(f"Report generated {ui.pretty_date(report['generated'])} from NYC Open Data extracts: HPD complaints (ygpa-z7cr), "
               "HPD buildings (kj4p-ruqc) and PLUTO (64uk-42ks). Educational prototype; no university endorsement is implied.")
st.page_link("app.py", label="Return to Building Check", icon=":material/arrow_back:")
