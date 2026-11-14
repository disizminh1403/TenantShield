from pathlib import Path

import pandas as pd
import pytest

from tenantshield.data import (
    DataError, historical_count, load_data, normalize_address, normalize_id,
    search_buildings, validate_data,
)


@pytest.fixture
def source():
    # Synthetic records test edge cases only; these never enter the application CSV.
    return pd.DataFrame({
        "BuildingID": ["001", "2", "3"], "BIN": ["3000001", "3000001", "3000000"],
        "FullAddress": ["447A EXAMPLE STREET, BROOKLYN", "447A EXAMPLE STREET, BROOKLYN", "9 TEST AVENUE"],
        "PredictedRisk": ["0", "1", ".25"], "PastComplaints_Clean": ["0", "3", ""],
    })


@pytest.mark.parametrize(("value", "expected"), [("3.000002e6", "3000002"), ("316596.0", "316596"),
                                                 ("001", "001"), ("NA", "")])
def test_id_normalization(value, expected):
    assert normalize_id(value) == expected


@pytest.mark.parametrize("value", ["1.2", "-1", "infinity", "abc", "1e9999"])
def test_invalid_ids(value):
    with pytest.raises(DataError):
        normalize_id(value)


def test_address_normalization():
    assert normalize_address(" 447a  Example St., Brooklyn ") == "447A EXAMPLE STREET BROOKLYN"
    assert normalize_address("5th Ave") == "5 AVENUE"


def test_search_disambiguation_and_exact_bin(source):
    data, _ = validate_data(source)
    assert len(search_buildings(data, "447a example st")) == 2
    assert len(search_buildings(data, "3000001", "BIN")) == 2
    assert len(search_buildings(data, "300000", "BIN")) == 0
    assert len(search_buildings(data, "3000000", "BIN")) == 1
    assert search_buildings(data, "").empty
    assert search_buildings(data, ".*").empty
    assert search_buildings(data, "unmatched").empty


@pytest.mark.parametrize("value", ["", "NaN", "inf", "-0.01", "1.01", "bad"])
def test_invalid_predictions(source, value):
    source.loc[0, "PredictedRisk"] = value
    with pytest.raises(DataError, match="PredictedRisk"):
        validate_data(source)


def test_missing_schema_and_duplicate_id(source):
    with pytest.raises(DataError, match="required columns"):
        validate_data(source.drop(columns="BIN"))
    source.loc[1, "BuildingID"] = "001"
    with pytest.raises(DataError, match="Duplicate"):
        validate_data(source)


def test_missing_address_keeps_bin_lookup(source):
    source.loc[0, "FullAddress"] = "NA"
    data, warnings = validate_data(source)
    assert warnings and data.loc["001", "FullAddress"] == ""
    assert len(search_buildings(data, "3000001", "BIN")) == 2


def test_missing_history_not_invented(source):
    data, _ = validate_data(source)
    assert historical_count(data.loc["001"], "PastComplaints_Clean", "HasPriorSeasonHistory") == "0 / unknown"
    assert historical_count(data.loc["2"], "PastComplaints_Clean", "HasPriorSeasonHistory") == "3"
    assert historical_count(data.loc["3"], "PastComplaints_Clean", "HasPriorSeasonHistory") == "Unavailable"
    row = pd.Series({"PastComplaints_Clean": 0, "HasPriorSeasonHistory": 1})
    assert historical_count(row, "PastComplaints_Clean", "HasPriorSeasonHistory") == "0"
    row["HasPriorSeasonHistory"] = 0
    assert historical_count(row, "PastComplaints_Clean", "HasPriorSeasonHistory") == "Unavailable"


def test_invalid_optional_values_become_unavailable(source):
    source["LegalStories"] = ["bad", "-1", "inf"]
    data, warnings = validate_data(source)
    assert data.LegalStories.isna().all() and warnings


def test_supplied_csv():
    path = Path(__file__).resolve().parents[1] / "TenantShield_App_Data.csv"
    data, warnings = load_data(path)
    assert len(data) == 135367
    assert not warnings
    assert data.BuildingID.is_unique
    assert data.PredictedRisk.between(0, 1).all()
    row = search_buildings(data, "3000002", "BIN").iloc[0]
    assert row.BuildingID == "316596"
    assert row.FullAddress == "10 JAY STREET, BROOKLYN"
    assert row.PredictedRisk == pytest.approx(0.041095782071352005)
    assert search_buildings(data, "10 Jay St").iloc[0].BuildingID == "316596"
