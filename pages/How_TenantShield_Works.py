"""Read-only methodology page; all reported metrics come from the project handoff."""

import streamlit as st

from tenantshield.design import apply_design, section
from tenantshield.methodology import FEATURES, METRICS, capture_chart, process_diagram, evaluation_timeline


st.set_page_config(page_title="How TenantShield Works | TenantShield", page_icon=":material/menu_book:", layout="wide")
apply_design(page="methodology")

st.markdown('<div class="ts-eyebrow"><span class="ts-accent"></span>TENANTSHIELD / RESEARCH & METHODOLOGY</div>',
            unsafe_allow_html=True)
st.title("How TenantShield Works")
st.markdown("From public building records to an informed starting point for renters. "
            "Understand what the model estimates, how it was evaluated, and where its limits matter.")
st.markdown('<span class="ts-badge">2025–26 held-out evaluation</span>'
            '<span class="ts-badge">2026–27 deployment outlook</span>'
            '<span class="ts-badge">Building-level estimates</span>', unsafe_allow_html=True)

with st.container(border=True, key="method_target"):
    section("A / What TenantShield predicts", "risk", "prediction-target")
    st.markdown("TenantShield estimates the **probability of at least one recorded HPD heating or hot-water "
                "complaint** for a Brooklyn residential building during the **2026–27 NYC heating season**.")
    st.markdown('<div class="ts-risk-note"><strong>The outcome is a recorded complaint.</strong> '
                'It is not a verified heating-system failure, an apartment-level probability, '
                'or an assessment that a home is safe or unsafe.</div>', unsafe_allow_html=True)
    st.caption("The outcome is binary for each building and season: at least one recorded complaint versus none recorded. "
               "The score does not predict the number of complaints or their severity.")

with st.container(border=True, key="method_data"):
    section("B / Our data and method", "building", "data-method")
    st.markdown("**Unit of analysis:** one building × heating season. "
                "**Historical modeling period:** 2022–23 through 2025–26. "
                "**Selected model:** an XGBoost binary classifier.")
    st.html(process_diagram())
    st.markdown("#### Public data, with distinct roles")
    st.markdown("""
- **[NYC HPD complaint records](https://data.cityofnewyork.us/resource/ygpa-z7cr):** heating/hot-water complaint outcomes and prior-season complaint history, aggregated using unique complaint IDs.
- **[HPD building registry](https://data.cityofnewyork.us/resource/kj4p-ruqc):** building identifiers, addresses and residential-unit information.
- **[HPD heating/hot-water violation records](https://data.cityofnewyork.us/resource/wvxf-dwi5):** evaluated during development. **Violation features were excluded from the selected final model.**
- **[NYC Building Footprints](https://data.cityofnewyork.us/resource/5zhs-2jue):** construction-year information used for historical eligibility; construction year is not one of the six final predictors.
    """)
    st.markdown("#### The six final predictors")
    st.html(FEATURES)
    st.caption("For the 2026–27 predictions, prior-season history refers to 2025–26 and two-seasons-prior history "
               "refers to 2024–25. No outcome-season complaint count or outcome label is used as a predictor.")
    st.info("Missing historical counts were filled with zero for modeling, while history-availability flags "
            "were retained. The dashboard CSV omits those flags, so a cleaned zero is displayed as “0 / unknown”. "
            "Missing history is never evidence of zero complaints.")

with st.container(border=True, key="method_evaluation"):
    section("C / How we evaluated the model", "history", "evaluation")
    st.markdown("**Chronological evaluation** separates model development from the final historical test.")
    st.html(evaluation_timeline())
    st.markdown("After validation, the model specification was fixed and refit using **2022–23 through 2024–25**, "
                "then evaluated once on the untouched **2025–26** season. For deployment, the fixed specification "
                "was refit using **2022–23 through 2025–26** to produce the **2026–27** predictions.")
    st.markdown('<div class="ts-risk-note"><strong>Test results are historical.</strong> All performance values below '
                'come from the held-out 2025–26 season. They do not measure the future 2026–27 predictions. '
                'Training and scoring happened outside this web app.</div>', unsafe_allow_html=True)

with st.container(border=True, key="method_performance"):
    section("D / Model performance", "risk", "performance")
    st.caption("FINAL HELD-OUT TEST · 2025–26 · 135,367 buildings · 13,326 positive outcomes, per project handoff")
    for group in (METRICS[:4], METRICS[4:]):
        for column, (label, value, explanation) in zip(st.columns(len(group)), group):
            column.metric(label, value, help=explanation)
    st.markdown("#### Finding complaint buildings in the highest-scored 10%")
    st.html(capture_chart())
    st.markdown("Selecting the **highest-scored 10% of test buildings** captured **56.3% of all test buildings "
                "with at least one recorded complaint**: this is top-decile **recall**. "
                "Among those selected buildings, **55.4%** had a recorded complaint: this is top-decile **precision**.")
    st.caption("Random selection of 10% of buildings is expected to capture approximately 10% of complaint-positive "
               "buildings. This is a theoretical benchmark, not a reported random-selection experiment. "
               "The chart compares recall, not precision or individual-building probabilities.")
    with st.expander("How to read the metrics"):
        for label, _, explanation in METRICS:
            st.markdown(f"**{label}.** {explanation}")
        st.markdown("Ranking performance and probability calibration are different properties. A model can rank "
                    "buildings usefully while its probabilities remain imperfectly calibrated. The project handoff "
                    "reports underprediction in test deciles; the scores should therefore remain provisional.")
    st.info("These values measure historical test-set performance. They are not guarantees of future performance "
            "or the condition of any particular building.")

with st.container(border=True, key="method_limits"):
    section("E / Limitations and responsible use", "shield", "responsible-use")
    st.markdown("""
- **Complaints are not verified failures.** A recorded complaint reflects a report, not necessarily an independently confirmed heating-system breakdown.
- **Reporting bias matters.** Tenant awareness, willingness and ability to report may differ across buildings. An absence of reports does not prove an absence of problems.
- **Building size affects exposure.** Larger buildings have more apartments and potential reporters, so they may naturally accumulate more complaints. These probabilities describe buildings, not individual apartments.
- **Calibration is imperfect.** Estimated probabilities may overstate or understate observed complaint frequencies; a strong ranking metric does not establish calibrated probabilities.
- **History may not repeat.** Building conditions, management, occupancy, recorded characteristics and reporting patterns can change. Historical snapshots may not reflect current conditions.
- **Coverage and selection are limited.** Present-day registries can create survivor/selection bias and look-ahead limitations. Construction-year eligibility is only a proxy for historical presence. The scored cohort may omit newly eligible buildings.
- **Use as context, not a safety guarantee.** Combine these estimates with current records, an inspection and conversations with tenants. They do not establish apartment-level safety or replace direct due diligence.
    """)
    st.markdown('<div class="ts-risk-note"><strong>Educational and research prototype.</strong> '
                'TenantShield offers provisional building-level estimates for exploration, not certified building assessments '
                'or guarantees of heating reliability. No university endorsement is implied.</div>', unsafe_allow_html=True)

st.caption("Evidence note: model specification, preprocessing and reported test metrics are documented in the supplied "
           "PROJECT_CONTEXT.md and project performance summary. The linked NYC datasets identify the underlying sources; "
           "they do not independently validate these metrics. This page reports the supplied results exactly and does "
           "not recompute them from the deployment CSV or run additional experiments.")
st.page_link("app.py", label="Return to building explorer", icon=":material/arrow_back:")
