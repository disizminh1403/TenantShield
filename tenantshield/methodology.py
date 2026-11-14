"""Reported research facts and responsive explanatory figures, not model computation."""


# Exact user-supplied held-out values, corroborated by PROJECT_CONTEXT.md.
METRICS = (
    ("ROC-AUC", "0.836", "Measures how well scores rank complaint-positive buildings above complaint-negative buildings across thresholds. Higher is better; it is not a percentage of correct predictions."),
    ("PR-AUC", "0.592", "Summarizes the precision–recall trade-off across thresholds. Higher is better; interpretation depends on outcome prevalence."),
    ("Log Loss", "0.219", "Evaluates predicted probabilities, penalizing confident incorrect predictions more heavily. Lower is better."),
    ("Brier Score", "0.0585", "Mean squared difference between predicted probability and the binary outcome. Lower is better; it reflects more than calibration alone."),
    ("Top-decile recall", "56.3%", "Among all complaint-positive buildings, the share captured in the highest-scored 10% of buildings."),
    ("Top-decile precision", "55.4%", "Among buildings in the highest-scored 10%, the share with at least one recorded complaint."),
    ("Positive outcome prevalence", "9.84%", "Share of all held-out test buildings with at least one recorded complaint. This is an observed outcome rate, not the mean model score."),
)

FEATURES = """<dl class="ts-feature-list">
<div><dt><code>PastComplaints_Clean</code></dt><dd>Cleaned count of complaints in the previous heating season.</dd></div>
<div><dt><code>Complaints2SeasonsAgo_Clean</code></dt><dd>Cleaned count of complaints two heating seasons earlier.</dd></div>
<div><dt><code>LogUnits</code></dt><dd>Log-transformed residential-unit count, log(1 + units); nonpositive or missing unit counts are imputed using the training-data median.</dd></div>
<div><dt><code>MissingUnits</code></dt><dd>Indicator for missing or nonpositive residential-unit information.</dd></div>
<div><dt><code>HasPriorSeasonHistory</code></dt><dd>Indicator that prior-season history is available; distinguishes unavailable history from an observed zero.</dd></div>
<div><dt><code>HasTwoSeasonsHistory</code></dt><dd>Indicator that history from two seasons earlier is available.</dd></div>
</dl>"""


def process_diagram() -> str:
    return """<ol class="ts-method-flow" aria-label="Data to prediction pipeline">
<li><span>01 / DATA</span><strong>Public building records</strong><p>Complaints, registry and footprints; violations evaluated in development.</p></li>
<li><span>02 / FEATURES</span><strong>Six final predictors</strong><p>Complaint history, unit counts and missing-history indicators.</p></li>
<li><span>03 / MODEL</span><strong>XGBoost classifier</strong><p>A fixed specification, trained outside the application.</p></li>
<li><span>04 / PREDICTION</span><strong>2026–27 probability</strong><p>At least one recorded heating or hot-water complaint.</p></li>
</ol>"""


def evaluation_timeline() -> str:
    return """<ol class="ts-method-flow ts-timeline" aria-label="Chronological evaluation timeline">
<li><span>INITIAL TRAINING</span><strong>2022–23 &amp; 2023–24</strong><p>Fit candidate models on earlier seasons.</p></li>
<li><span>VALIDATION</span><strong>2024–25</strong><p>Evaluate development choices before fixing the model specification.</p></li>
<li><span>HELD-OUT TEST</span><strong>2025–26</strong><p>One final evaluation after refitting on training and validation seasons.</p></li>
<li><span>DEPLOYMENT</span><strong>2026–27</strong><p>Precomputed estimates after refitting through 2025–26. No future test results.</p></li>
</ol>"""


def capture_chart() -> str:
    # Both bars share the same 0–100% scale. Random selection is an expectation, not an experiment.
    return """<figure class="ts-capture-chart" aria-label="Share of complaint-positive test buildings captured: highest-scored 10 percent captures 56.3 percent; random 10 percent selection captures approximately 10 percent in expectation.">
<figcaption>Share of all complaint-positive test buildings captured</figcaption>
<div class="ts-bar-label"><span>Highest-scored 10% of buildings</span><strong>56.3%</strong></div>
<div class="ts-bar-track"><div class="ts-bar-model" style="width:56.3%"></div></div>
<div class="ts-bar-label"><span>Random 10% selection · expected</span><strong>≈10%</strong></div>
<div class="ts-bar-track"><div class="ts-bar-random" style="width:10%"></div></div>
<div class="ts-bar-axis" aria-hidden="true"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>
<p>Same selection size: 10% of test buildings. Different share of complaint buildings reached.</p>
</figure>"""
