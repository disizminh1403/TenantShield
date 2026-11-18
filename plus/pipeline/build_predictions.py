"""Build the precomputed TenantShield Plus estimates. Offline only; the web app never trains.

Run from the repository root after fetch_open_data.py:

    python plus/pipeline/build_predictions.py

Inputs : TenantShield_App_Data.csv (the scored cohort; never modified) and plus/raw_data/*.csv
Outputs: plus/data/plus_predictions.csv  one row per BuildingID
         plus/data/plus_report.json      backtest evidence and summary statistics

Design rules
- Chronological evaluation: train on outcome seasons 2023–24 and 2024–25, test once on 2025–26,
  then refit on 2023–24 through 2025–26 to score 2026–27.
- Every predictor is measured strictly before the outcome window it predicts.
- The original PredictedRisk is never changed. These are companion estimates from separate models.
"""

from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor,
                              RandomForestClassifier)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, log_loss,
                             mean_absolute_error, mean_poisson_deviance, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "plus" / "raw_data"
OUT = ROOT / "plus" / "data"

CHRONIC = 5                      # "chronic" = this many or more recorded complaints in one heating season
TRAIN, TEST, DEPLOY = (2023, 2024), 2025, 2026   # seasons are named by the year their October falls in
HISTORY = (2020, 2021, 2022, 2023, 2024, 2025)   # complete seasons available for display
GB = dict(max_iter=300, max_depth=4, learning_rate=0.03, min_samples_leaf=20, random_state=0)

SIX = ["c1", "c2", "log_units", "missing_units", "has1", "has2"]        # mirrors the original model's inputs
RICH = ["c1", "c2", "c3", "apts1", "bw1", "months1", "off1", "units", "stories", "year", "zip_rate1"]
NOWCAST = RICH + ["todate", "todate_apts"]
SCORE_BINS = [0, .02, .05, .10, .20, .35, .50, .70, .85, 1.0001]
COUNT_BINS = [0, .1, .25, .5, 1, 2, 5, 10, 20, 50, np.inf]


def label(season: int) -> str:
    return f"{season}–{str(season + 1)[-2:]}"


def load_cohort() -> pd.DataFrame:
    cohort = pd.read_csv(ROOT / "TenantShield_App_Data.csv", dtype=str, keep_default_na=False)
    for source, name in (("LegalClassA", "units"), ("LegalStories", "stories"), ("Construction Year", "year"),
                         ("PredictedRisk", "PredictedRisk")):
        cohort[name] = pd.to_numeric(cohort[source], errors="coerce")
    cohort.loc[cohort.units <= 0, "units"] = np.nan       # zero residential units is treated as unknown
    cohort.loc[cohort.stories <= 0, "stories"] = np.nan
    return cohort.set_index("BuildingID")[["BIN", "Zip", "units", "stories", "year", "PredictedRisk"]]


def load_complaints() -> tuple[pd.DataFrame, pd.Timestamp]:
    rows = pd.read_csv(RAW / "complaints.csv", dtype=str, keep_default_na=False)
    rows["received"] = pd.to_datetime(rows.received_date)
    # Keep whole days only: the newest day in an extract is still filling in.
    cut = rows.received.max().normalize()
    rows = rows[rows.received < cut].copy()
    month = rows.received.dt.month
    rows["season"] = np.where(month >= 10, rows.received.dt.year, rows.received.dt.year - 1)
    rows["heating"] = (month >= 10) | (month <= 5)        # NYC heat season: October 1 through May 31
    rows["month"] = month
    return rows, cut


def aggregate(rows: pd.DataFrame, prefix: str = "") -> pd.DataFrame:
    """Per building and season: distinct complaints, distinct apartments, building-wide complaints, active months."""
    apartments = rows[rows.unit_type.eq("APARTMENT") & ~rows.apartment.isin(["", "BLDG"])]
    wide = rows[rows.unit_type.eq("BUILDING-WIDE")]
    keys = ["building_id", "season"]
    return pd.DataFrame({
        prefix + "n": rows.groupby(keys).complaint_id.nunique(),
        prefix + "apts": apartments.groupby(keys).apartment.nunique(),
        prefix + "bw": wide.groupby(keys).complaint_id.nunique(),
        prefix + "months": rows.groupby(keys).month.nunique(),
    }).fillna(0)


def season_frame(season: int, cohort: pd.DataFrame, tables: dict, with_outcome: bool = True) -> pd.DataFrame:
    """Predictors known before `season` starts, plus outcomes when the season has been observed."""
    frame = cohort[cohort.year < season].copy()           # the project's conservative eligibility proxy
    ids = frame.index

    def pick(table: str, column: str, at: int) -> np.ndarray:
        source = tables[table]
        index = pd.MultiIndex.from_arrays([ids, np.full(len(ids), at)])
        return source[column].reindex(index).fillna(0).to_numpy()

    for lag in (1, 2, 3):
        frame[f"c{lag}"] = pick("heating", "n", season - lag)
    frame["apts1"] = pick("heating", "apts", season - 1)
    frame["bw1"] = pick("heating", "bw", season - 1)
    frame["months1"] = pick("heating", "months", season - 1)
    frame["off1"] = pick("off", "n", season - 1)          # June–September immediately before this season
    frame["zip_rate1"] = (frame.c1 > 0).groupby(frame.Zip).transform("mean")
    frame["has1"] = (frame.year < season - 1).astype(int)
    frame["has2"] = (frame.year < season - 2).astype(int)
    frame["missing_units"] = frame.units.isna().astype(int)
    frame["todate"] = pick("todate", "n", season)         # October 1 to the same calendar cut as today
    frame["todate_apts"] = pick("todate", "apts", season)
    if with_outcome:
        frame["n"] = pick("heating", "n", season)
        frame["rest"] = pick("rest", "n", season)
    frame["season"] = season
    return frame


def add_log_units(train: pd.DataFrame, *others: pd.DataFrame) -> None:
    median = train.units.median()                         # training-only median, as in the original pipeline
    for frame in (train, *others):
        frame["log_units"] = np.log1p(frame.units.fillna(median))


def classification_metrics(actual: np.ndarray, score: np.ndarray) -> dict:
    top = np.argsort(-score, kind="stable")[: len(score) // 10]
    return {
        "n": int(len(actual)), "positives": int(actual.sum()), "prevalence": float(actual.mean()),
        "roc_auc": float(roc_auc_score(actual, score)), "pr_auc": float(average_precision_score(actual, score)),
        "log_loss": float(log_loss(actual, np.clip(score, 1e-6, 1 - 1e-6))),
        "brier": float(brier_score_loss(actual, score)),
        "top_decile_precision": float(actual[top].mean()), "top_decile_recall": float(actual[top].sum() / actual.sum()),
    }


def reliability(actual: np.ndarray, score: np.ndarray, minimum: int = 200) -> list[dict]:
    """Observed outcome rate by score band. Bands with fewer than `minimum` buildings are merged upward
    into their neighbour so that every reported rate rests on a reasonable sample."""
    bins = pd.cut(score, SCORE_BINS, right=False)
    table = pd.DataFrame({"actual": actual, "score": score}).groupby(bins, observed=False)
    bands = []
    for group, part in table:
        band = {"low": float(group.left), "high": float(min(group.right, 1)), "n": int(len(part)),
                "score_sum": float(part.score.sum()), "actual_sum": float(part.actual.sum())}
        if bands and (band["n"] < minimum or bands[-1]["n"] < minimum):
            last = bands[-1]
            last.update(high=band["high"], n=last["n"] + band["n"], score_sum=last["score_sum"] + band["score_sum"],
                        actual_sum=last["actual_sum"] + band["actual_sum"])
        else:
            bands.append(band)
    return [{"low": b["low"], "high": b["high"], "n": b["n"], "mean_score": b["score_sum"] / b["n"],
             "observed_rate": b["actual_sum"] / b["n"]} for b in bands if b["n"]]


class CountModel:
    """Expected complaints per season.

    Complaint counts are extremely skewed (most buildings 0, a few above 500), and a Poisson
    boosting objective diverged on them. This fits log(1 + count) instead, then applies one
    scaling factor learned on the training rows so that predictions add up to the training total.
    """

    def __init__(self) -> None:
        self.model = HistGradientBoostingRegressor(**{**GB, "learning_rate": 0.1})
        self.scale = 1.0

    def _raw(self, x: pd.DataFrame) -> np.ndarray:
        return np.clip(np.expm1(self.model.predict(x)), 0.001, None)   # a strictly positive floor

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "CountModel":
        self.model.fit(x, np.log1p(y))
        self.scale = float(y.sum() / self._raw(x).sum())
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return self._raw(x) * self.scale


def history_check(cohort_csv: pd.DataFrame, rows: pd.DataFrame) -> dict:
    """How closely this public extract reproduces the two history columns already in the app CSV.

    Each column is compared against two candidate windows, because the two columns turn out to
    follow different ones: 1 October–31 May (the heating season) and 1 October–30 September.
    """
    result = {}
    for column, season in (("PastComplaints_Clean", 2025), ("Complaints2SeasonsAgo_Clean", 2024)):
        published = pd.to_numeric(cohort_csv[column], errors="coerce")
        start = pd.Timestamp(season, 10, 1)
        entry = {"csv_column": column, "csv_total": int(published.sum())}
        for name, end in (("oct_to_may", pd.Timestamp(season + 1, 6, 1)), ("oct_to_sep", pd.Timestamp(season + 1, 10, 1))):
            window = rows[(rows.received >= start) & (rows.received < end)]
            mine = window.groupby("building_id").complaint_id.nunique().reindex(cohort_csv.index).fillna(0)
            entry[name] = {"exact_match_share": float(mine.eq(published).mean()), "extract_total": int(mine.sum()),
                           "buildings_differing": int(mine.ne(published).sum())}
        result[label(season)] = entry
    return result


def models(features: list[str]) -> dict:
    return {
        "Gradient boosting": lambda: HistGradientBoostingClassifier(**GB),
        "Random forest": lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=20, max_features="sqrt",
                                                        n_jobs=-1, random_state=0),
        "Logistic regression": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    }


def prepared(frame: pd.DataFrame, features: list[str], name: str, medians: pd.Series) -> pd.DataFrame:
    x = frame[features]
    if name == "Gradient boosting":
        return x                                          # handles missing values natively
    x = x.fillna(medians)
    if name == "Logistic regression":
        skewed = [c for c in features if c not in ("log_units", "missing_units", "has1", "has2", "year", "zip_rate1")]
        x = x.assign(**{c: np.log1p(x[c]) for c in skewed})
    return x


def compare(train: pd.DataFrame, test: pd.DataFrame, target: str, feature_sets: dict) -> tuple[list[dict], dict]:
    """Fit every model family on the training seasons and score the held-out season."""
    results, scores = [], {}
    for set_name, features in feature_sets.items():
        medians = train[features].median()
        for name, make in models(features).items():
            model = make().fit(prepared(train, features, name, medians), train[target])
            score = model.predict_proba(prepared(test, features, name, medians))[:, 1]
            scores[(set_name, name)] = score
            results.append({"features": set_name, "model": name,
                            **classification_metrics(test[target].to_numpy(), score)})
            print(f"  {target:8s} {set_name:22s} {name:20s} ROC {results[-1]['roc_auc']:.3f}  "
                  f"PR {results[-1]['pr_auc']:.3f}", flush=True)
    return results, scores


def main() -> None:
    cohort = load_cohort()
    rows, cut = load_complaints()
    offset = cut - pd.Timestamp(DEPLOY, 10, 1)            # same day-of-season cut in every season
    season_start = pd.to_datetime(rows.season.astype(str) + "-10-01")
    before_cut = rows.received < season_start + offset
    heating = rows[rows.heating]
    tables = {
        "heating": aggregate(heating),
        "off": aggregate(rows[~rows.heating]),
        "todate": aggregate(heating[before_cut[heating.index]]),
        "rest": aggregate(heating[~before_cut[heating.index]]),
    }
    frames = {s: season_frame(s, cohort, tables) for s in (*TRAIN, TEST)}
    for frame in frames.values():
        frame["y1"] = (frame.n >= 1).astype(int)
        frame["y5"] = (frame.n >= CHRONIC).astype(int)
        frame["yrest"] = (frame.rest >= 1).astype(int)
    train = pd.concat([frames[s] for s in TRAIN])
    test = frames[TEST]
    add_log_units(train, test)

    csv_history = pd.read_csv(ROOT / "TenantShield_App_Data.csv", dtype=str, keep_default_na=False).set_index("BuildingID")
    report = {
        "generated": date.today().isoformat(),
        "history_check": history_check(csv_history, rows),
        "data_through": (cut - pd.Timedelta(days=1)).date().isoformat(),
        "chronic_threshold": CHRONIC,
        "train_seasons": [label(s) for s in TRAIN], "test_season": label(TEST), "deploy_season": label(DEPLOY),
        "features": {"original_six": SIX, "expanded": RICH, "nowcast": NOWCAST},
    }

    # ---- Backtest: train 2023–24 + 2024–25, test 2025–26 -------------------------------------
    print("Backtest on", label(TEST))
    any_results, any_scores = compare(train, test, "y1", {"Original six inputs": SIX, "Expanded history": RICH})
    chronic_results, chronic_scores = compare(train, test, "y5", {"Expanded history": RICH})
    now_results, now_scores = compare(train, test, "yrest", {"Pre-season only": RICH, "With season to date": NOWCAST})
    rule = (test.c1 >= CHRONIC).to_numpy()
    actual5 = test.y5.to_numpy()
    report["backtest"] = {
        "any_complaint": any_results,
        "chronic": chronic_results,
        "chronic_rule_same_as_last_season": {
            "flagged": int(rule.sum()), "precision": float(actual5[rule].mean()),
            "recall": float(actual5[rule].sum() / actual5.sum())},
        "rest_of_season": [r for r in now_results if r["model"] == "Gradient boosting"],
        "chronic_reliability": reliability(actual5, chronic_scores[("Expanded history", "Gradient boosting")]),
        "rest_reliability": reliability(test.yrest.to_numpy(),
                                        now_scores[("With season to date", "Gradient boosting")]),
    }

    # Which inputs matter most for the chronic model: drop in held-out PR-AUC when one input is shuffled.
    chronic_backtest = HistGradientBoostingClassifier(**GB).fit(train[RICH], train.y5)
    sample = test.sample(40_000, random_state=0)
    shuffled = permutation_importance(chronic_backtest, sample[RICH], sample.y5, scoring="average_precision",
                                      n_repeats=3, random_state=0)
    report["backtest"]["chronic_importance"] = sorted(
        ({"feature": name, "pr_auc_drop": float(drop)} for name, drop in zip(RICH, shuffled.importances_mean)),
        key=lambda item: -item["pr_auc_drop"])

    counter = CountModel().fit(train[RICH], train.n)
    expected = counter.predict(test[RICH])
    actual_n = test.n.to_numpy()
    constant = np.full(len(test), train.n.mean())
    bins = pd.DataFrame({"actual": actual_n, "expected": expected}).groupby(
        pd.cut(expected, COUNT_BINS, right=False), observed=True)
    report["backtest"]["count"] = {
        "mae_model": float(mean_absolute_error(actual_n, expected)),
        "mae_same_as_last_season": float(mean_absolute_error(actual_n, test.c1)),
        "poisson_deviance_model": float(mean_poisson_deviance(actual_n, expected)),
        "poisson_deviance_training_mean": float(mean_poisson_deviance(actual_n, constant)),
        "total_expected": float(expected.sum()), "total_actual": int(actual_n.sum()),
        "top_decile_share_of_complaints": float(
            actual_n[np.argsort(-expected, kind="stable")[: len(expected) // 10]].sum() / actual_n.sum()),
        "bins": [{"low": float(g.left), "high": None if np.isinf(g.right) else float(g.right), "n": int(len(p)),
                  "mean_expected": float(p.expected.mean()), "mean_actual": float(p.actual.mean()),
                  "p25": float(p.actual.quantile(.25)), "p50": float(p.actual.quantile(.5)),
                  "p75": float(p.actual.quantile(.75)), "p90": float(p.actual.quantile(.9))} for g, p in bins],
    }
    print(f"  count: MAE {report['backtest']['count']['mae_model']:.3f} vs same-as-last-season "
          f"{report['backtest']['count']['mae_same_as_last_season']:.3f}")

    # ---- Deployment: refit through 2025–26, score 2026–27 ------------------------------------
    full = pd.concat([train, test])
    deploy = season_frame(DEPLOY, cohort, tables, with_outcome=False)
    add_log_units(full, deploy)
    chronic_model = HistGradientBoostingClassifier(**GB).fit(full[RICH], full.y5)
    count_model = CountModel().fit(full[RICH], full.n)
    rest_model = HistGradientBoostingClassifier(**GB).fit(full[NOWCAST], full.yrest)
    six_model = HistGradientBoostingClassifier(**GB).fit(full[SIX], full.y1)
    replica = six_model.predict_proba(deploy[SIX])[:, 1]
    report["replication_check"] = {
        "note": "A Python gradient-boosting model refit on the original six inputs, compared with the "
                "R/XGBoost PredictedRisk already in the app CSV. Agreement supports the data reconstruction.",
        "pearson": float(np.corrcoef(replica, deploy.PredictedRisk)[0, 1]),
        "spearman": float(pd.Series(replica).corr(deploy.PredictedRisk.reset_index(drop=True), method="spearman")),
        "mean_abs_difference": float(np.abs(replica - deploy.PredictedRisk).mean()),
    }

    # Early real-world check of the ORIGINAL score: it was fixed before this season began.
    early = (deploy.todate >= 1).to_numpy().astype(int)
    report["early_season_check"] = {
        "window": f"{DEPLOY}-10-01 through {report['data_through']}",
        **classification_metrics(early, deploy.PredictedRisk.to_numpy()),
        "reliability": reliability(early, deploy.PredictedRisk.to_numpy()),
    }
    # Log loss and Brier score would compare a full-season probability with a partial-season outcome.
    for unsuitable in ("log_loss", "brier"):
        report["early_season_check"].pop(unsuitable)

    output = pd.DataFrame(index=cohort.index)
    output["ChronicRisk"] = pd.Series(chronic_model.predict_proba(deploy[RICH])[:, 1], deploy.index).round(4)
    output["ExpectedComplaints"] = pd.Series(count_model.predict(deploy[RICH]), deploy.index).round(3)
    output["RestOfSeasonRisk"] = pd.Series(rest_model.predict_proba(deploy[NOWCAST])[:, 1], deploy.index).round(4)
    output["SeasonToDate"] = deploy.todate.astype(int)
    output["SeasonToDateApartments"] = deploy.todate_apts.astype(int)
    for season in HISTORY:
        index = pd.MultiIndex.from_arrays([cohort.index, np.full(len(cohort), season)])
        counts = pd.Series(tables["heating"].n.reindex(index).fillna(0).to_numpy(), cohort.index)
        output[f"Complaints{season}"] = counts.where(cohort.year < season).astype("Int64")   # blank before eligibility
    output["Apartments2025"] = deploy.apts1.astype(int)
    output["BuildingWide2025"] = deploy.bw1.astype(int)
    output["OffSeason2026"] = deploy.off1.astype(int)

    # Approximate location: HPD registry block/lot -> tax lot (BBL) -> PLUTO coordinate. A bulk join, not geocoding.
    registry = pd.read_csv(RAW / "buildings.csv", dtype=str, keep_default_na=False).drop_duplicates("buildingid")
    registry = registry[registry.block.str.isdigit() & registry.lot.str.isdigit()]
    registry["bbl"] = "3" + registry.block.str.zfill(5) + registry.lot.str.zfill(4)
    pluto = pd.read_csv(RAW / "pluto.csv", dtype=str, keep_default_na=False)
    pluto["bbl"] = pluto.bbl.str.split(".").str[0]
    pluto = pluto.drop_duplicates("bbl").set_index("bbl")
    lots = registry.set_index("buildingid").bbl.reindex(cohort.index)
    for column, name in (("latitude", "Latitude"), ("longitude", "Longitude")):
        values = pd.to_numeric(lots.map(pluto[column]), errors="coerce")
        output[name] = values.round(6).to_numpy()
    plausible = output.Latitude.between(40.55, 40.75) & output.Longitude.between(-74.06, -73.83)
    output.loc[~plausible, ["Latitude", "Longitude"]] = np.nan

    # ---- Summary statistics for the methodology page and the class presentation ----------------
    history = pd.concat([frames[s] for s in (*TRAIN, TEST)])
    report["seasons"] = [{
        "season": label(s), "buildings": int(len(f)), "complaints": int(f.n.sum()),
        "any_rate": float(f.y1.mean()), "chronic_rate": float(f.y5.mean()),
        "share_of_complaints_from_chronic": float(f.n[f.y5 == 1].sum() / f.n.sum()),
    } for s, f in history.groupby("season")]
    size = pd.cut(test.units, [0, 2, 5, 19, 49, np.inf], labels=["1–2", "3–5", "6–19", "20–49", "50+"])
    era = pd.cut(test.year, [0, 1919, 1939, 1969, 1999, 3000],
                 labels=["Before 1920", "1920–39", "1940–69", "1970–99", "2000 or later"])
    report["rates_2025"] = {
        "by_units": [{"group": str(g), "buildings": int(len(p)), "any_rate": float(p.y1.mean()),
                      "chronic_rate": float(p.y5.mean()), "complaints_per_100_units": float(100 * p.n.sum() / p.units.sum())}
                     for g, p in test.groupby(size, observed=True)],
        "by_era": [{"group": str(g), "buildings": int(len(p)), "any_rate": float(p.y1.mean()),
                    "chronic_rate": float(p.y5.mean())} for g, p in test.groupby(era, observed=True)],
    }
    report["persistence_2025"] = {
        "any_given_any_last_season": float(test.y1[test.c1 >= 1].mean()),
        "any_given_none_last_season": float(test.y1[test.c1 == 0].mean()),
        "chronic_given_chronic_last_season": float(test.y5[test.c1 >= CHRONIC].mean()),
        "chronic_given_not_chronic_last_season": float(test.y5[test.c1 < CHRONIC].mean()),
    }
    pooled = heating[heating.season.between(2021, 2025)].drop_duplicates("complaint_id")
    monthly = pooled.month.value_counts(normalize=True)
    report["monthly_share"] = [{"month": name, "share": float(monthly.get(number, 0))} for number, name in
                               zip((10, 11, 12, 1, 2, 3, 4, 5), ("Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"))]
    report["deployment"] = {
        "buildings": int(len(output)), "with_coordinates": int(output.Latitude.notna().sum()),
        "season_to_date_buildings": int((output.SeasonToDate > 0).sum()),
        "season_to_date_complaints": int(output.SeasonToDate.sum()),
        "chronic_risk_median": float(output.ChronicRisk.median()), "chronic_risk_max": float(output.ChronicRisk.max()),
        "expected_complaints_total": float(output.ExpectedComplaints.sum()),
    }

    OUT.mkdir(exist_ok=True)
    output.to_csv(OUT / "plus_predictions.csv", index_label="BuildingID")
    (OUT / "plus_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(output):,} buildings; data through {report['data_through']}")
    print(json.dumps({k: report[k] for k in ("replication_check", "early_season_check", "deployment")}, indent=1))


if __name__ == "__main__":
    main()
