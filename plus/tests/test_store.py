from pathlib import Path

import pandas as pd
import pytest

from tsplus import PLUS_DIR, REPO_ROOT, store
from tenantshield.data import DataError

BASE = """BuildingID,BIN,FullAddress,Zip,LegalClassA,LegalStories,Construction Year,PastComplaints_Clean,Complaints2SeasonsAgo_Clean,PredictedRisk
1,3000001,"1 TEST STREET, BROOKLYN",11201,10,4,1920,3,0,0.50
2,3000002,"2 TEST STREET, BROOKLYN",11201,2,2,1930,0,0,0.05
3,3000003,"3 FAR AVENUE, BROOKLYN",11233,60,6,1950,9,4,0.90
4,3000004,"4 NOWHERE ROAD, BROOKLYN",NA,0,3,1960,0,0,0.05
"""
PLUS = """BuildingID,ChronicRisk,ExpectedComplaints,RestOfSeasonRisk,SeasonToDate,SeasonToDateApartments,Complaints2024,Complaints2025,Apartments2025,BuildingWide2025,OffSeason2026,Latitude,Longitude
1,0.20,2.5,0.40,1,1,0,3,2,1,0,40.7000,-73.9900
2,0.01,0.05,0.03,0,0,0,0,0,0,0,40.7005,-73.9900
3,0.80,12.0,0.95,4,3,4,9,5,6,2,40.6800,-73.9300
"""


@pytest.fixture()
def paths(tmp_path: Path) -> tuple[Path, Path]:
    base, plus = tmp_path / "base.csv", tmp_path / "plus.csv"
    base.write_text(BASE, encoding="utf-8")
    plus.write_text(PLUS, encoding="utf-8")
    return base, plus


@pytest.fixture()
def frame(paths) -> pd.DataFrame:
    return store.load_all(*paths)[0]


def test_join_keeps_original_score_and_flags_missing_plus_rows(paths):
    frame, warnings = store.load_all(*paths)
    assert frame.loc["1", "PredictedRisk"] == 0.50 and frame.loc["1", "ChronicRisk"] == 0.20
    assert frame.index.tolist() == ["1", "2", "3", "4"] and isinstance(frame.loc["1", "BIN"], str)
    assert not store.has_plus(frame.loc["4"]) and store.has_plus(frame.loc["3"])
    assert any("1 buildings have no Plus estimates" in warning for warning in warnings)
    assert frame.loc["3", "ApartmentsLastSeason"] == 5 and frame.loc["3", "OffSeasonBefore"] == 2


@pytest.mark.parametrize("old,new,message", [
    ("0.20,2.5", "1.20,2.5", "ChronicRisk"),
    ("2.5,0.40", "-1,0.40", "ExpectedComplaints"),
    ("\n2,0.01", "\n1,0.01", "one row per BuildingID"),
    ("ChronicRisk,", "Chronic,", "missing columns"),
])
def test_invalid_plus_table_is_rejected(tmp_path, old, new, message):
    path = tmp_path / "plus.csv"
    path.write_text(PLUS.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(DataError, match=message):
        store.load_plus(path)


def test_out_of_range_coordinates_become_unavailable(tmp_path):
    path = tmp_path / "plus.csv"
    path.write_text(PLUS.replace("40.7000,-73.9900", "10.0,-73.9900"), encoding="utf-8")
    assert pd.isna(store.load_plus(path).loc["1", "Latitude"])


def test_size_bands_and_units():
    assert [store.size_band(v) for v in (1, 2, 3, 19, 20, 50, 900)] == [
        "1–2 units", "1–2 units", "3–5 units", "6–19 units", "20–49 units", "50+ units", "50+ units"]
    assert store.size_band(0) == store.size_band(None) == store.size_band(float("nan")) == store.UNKNOWN_SIZE
    assert store.per_100_units(3, 10) == 30 and store.per_100_units(3, 0) is None and store.per_100_units(3, None) is None


def test_share_below_never_counts_ties(frame):
    assert store.share_below(frame.PredictedRisk, 0.05) == 0          # two buildings tie at the minimum
    assert store.share_below(frame.PredictedRisk, 0.90) == 0.75
    assert pd.isna(store.share_below(frame.ChronicRisk, float("nan")))


def test_peer_groups_skip_missing_zip_and_unknown_size(frame):
    labels = [item["group"] for item in store.comparison(frame, frame.loc["1"], "PredictedRisk")]
    assert labels == ["All scored Brooklyn buildings", "ZIP 11201", "Buildings with 6–19 units"]
    assert [item["group"] for item in store.comparison(frame, frame.loc["4"], "PredictedRisk")] == [
        "All scored Brooklyn buildings"]


def test_score_and_count_bands():
    bands = [{"low": 0, "high": .1, "n": 5}, {"low": .1, "high": 1.0, "n": 7}]
    assert store.band_for(bands, 0.0)["n"] == 5 and store.band_for(bands, .1)["n"] == 7
    assert store.band_for(bands, 1.0)["n"] == 7 and store.band_for([], .5) is None
    bins = [{"low": 0, "high": 1}, {"low": 1, "high": None}]
    assert store.count_band(bins, .5)["high"] == 1 and store.count_band(bins, 400)["high"] is None


def test_nearby_uses_distance_and_excludes_self(frame):
    near = store.nearby(frame, frame.loc["1"], radius_m=100)
    assert near.index.tolist() == ["2"] and 50 <= near.DistanceM.iloc[0] <= 60   # 0.0005 degrees of latitude
    assert store.nearby(frame, frame.loc["1"], radius_m=20).empty
    assert store.nearby(frame, frame.loc["4"]).empty                             # no coordinates


def test_area_summary_ignores_missing_zip(frame):
    summary = store.area_summary(frame)
    assert set(summary.index) == {"11201", "11233"}
    assert summary.loc["11201", "Buildings"] == 2 and summary.loc["11201", "ComplaintLastSeasonShare"] == 0.5
    assert summary.loc["11233", "ComplaintsPer100Units"] == 15


def test_shipped_files_are_consistent():
    frame, warnings = store.load_all(REPO_ROOT / "TenantShield_App_Data.csv", PLUS_DIR / "data" / "plus_predictions.csv")
    report = store.load_report(PLUS_DIR / "data" / "plus_report.json")
    assert not warnings and frame.ChronicRisk.notna().all()
    assert frame.ChronicRisk.between(0, 1).all() and frame.RestOfSeasonRisk.between(0, 1).all()
    assert report["deployment"]["buildings"] == len(frame)
    assert report["deployment"]["season_to_date_complaints"] == int(frame.SeasonToDate.sum())
    # The last complete season in the Plus table reproduces the count already in the app CSV.
    last = store.season_columns(frame)[-1]
    assert frame[last].eq(frame.PastComplaints_Clean).mean() > 0.999
