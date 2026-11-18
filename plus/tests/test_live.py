from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from tsplus import live
from tenantshield.services import ServiceError


def response(payload, status=200):
    mock = Mock(status_code=status)
    mock.json.return_value = payload
    mock.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(response=mock)
    return mock


def test_season_start():
    assert live.season_start(date(2026, 11, 18)) == date(2026, 10, 1)
    assert live.season_start(date(2027, 3, 1)) == date(2026, 10, 1)
    assert live.season_start(date(2026, 9, 30)) == date(2025, 10, 1)


def test_complaints_are_deduplicated_and_apartment_numbers_dropped():
    rows = [
        {"complaint_id": "9", "received_date": "2026-11-07T08:00:00.000", "unit_type": "APARTMENT",
         "problem_code": "NO HEAT", "complaint_status": "OPEN", "apartment": "4B"},
        {"complaint_id": "9", "received_date": "2026-11-07T08:00:00.000", "unit_type": "APARTMENT",
         "problem_code": "NO HOT WATER", "complaint_status": "OPEN", "apartment": "4B"},
        {"complaint_id": "8", "received_date": "2026-10-20T21:30:00.000", "unit_type": "BUILDING-WIDE",
         "problem_code": "NO HEAT", "complaint_status": "CLOSE"},
        {"complaint_id": "7", "received_date": "not a date"},
    ]
    with patch("tsplus.live.requests.get", return_value=response(rows)) as get:
        records = live.heat_complaints("388518", date(2026, 11, 18), token="secret-token")
    assert [(c.scope, c.problem, c.status) for c in records.complaints] == [
        ("Apartment", "No Heat", "Open"), ("Building-wide", "No Heat", "Close")]
    assert not hasattr(records.complaints[0], "apartment") and not records.truncated
    params, headers = get.call_args.kwargs["params"], get.call_args.kwargs["headers"]
    assert "building_id='388518'" in params["$where"] and "2026-10-01" in params["$where"]
    assert headers["X-App-Token"] == "secret-token" and "secret-token" not in str(params)


def test_open_violations_flag_heat_related():
    rows = [{"class": "C", "inspectiondate": "2026-01-05T00:00:00.000", "novdescription": "PROVIDE  ADEQUATE SUPPLY OF HEAT"},
            {"class": "A", "novdescription": "PAINT THE CEILING"}]
    with patch("tsplus.live.requests.get", return_value=response(rows)):
        violations, truncated = live.open_violations("388518")
    assert [(v.violation_class, v.heat_related, v.inspected) for v in violations] == [
        ("C", True, date(2026, 1, 5)), ("A", False, None)]
    assert violations[0].description == "PROVIDE ADEQUATE SUPPLY OF HEAT" and not truncated


@pytest.mark.parametrize("bad", ["", "12 OR 1=1", "388518'", "abc"])
def test_only_numeric_building_ids_reach_the_query(bad):
    with patch("tsplus.live.requests.get", side_effect=AssertionError("must not be called")):
        with pytest.raises(ServiceError):
            live.heat_complaints(bad, date(2026, 11, 18))


def test_errors_never_expose_the_request():
    secret_url = "https://data.cityofnewyork.us/resource/x.json?$$app_token=SECRET"
    with patch("tsplus.live.requests.get", side_effect=requests.ConnectionError(secret_url)):
        with pytest.raises(ServiceError) as caught:
            live.open_violations("388518", token="SECRET")
    assert "SECRET" not in str(caught.value) and "http" not in str(caught.value)
    with patch("tsplus.live.requests.get", return_value=response([], status=429)):
        with pytest.raises(ServiceError, match="HTTP 429"):
            live.open_violations("388518")
    with patch("tsplus.live.requests.get", return_value=response({"error": True})):
        with pytest.raises(ServiceError, match="unexpected"):
            live.open_violations("388518")
