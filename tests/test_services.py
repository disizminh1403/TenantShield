from unittest.mock import Mock, patch

import pytest
import requests

from tenantshield import services
from tenantshield.services import Location, ServiceError, geocode, street_view


def response(payload=None, content=b"image bytes", content_type="image/jpeg"):
    result = Mock()
    result.json.return_value = payload
    result.content = content
    result.headers = {"Content-Type": content_type}
    return result


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(services.time, "sleep", lambda _: None)


def test_geocoder_match_and_out_of_area_filter():
    payload = {"result": {"addressMatches": [
        {"coordinates": {"x": -73.99, "y": 40.70}, "matchedAddress": "TEST ADDRESS"},
        {"coordinates": {"x": 0, "y": 0}, "matchedAddress": "OUTSIDE AREA"},
    ]}}
    with patch.object(services.requests, "get", return_value=response(payload)) as get:
        results = geocode("selected CSV address")
    assert len(results) == 1 and results[0].latitude == 40.70
    assert get.call_args.kwargs["params"]["address"] == "selected CSV address"


def test_geocoder_no_match_and_malformed():
    with patch.object(services.requests, "get", return_value=response({"result": {"addressMatches": []}})):
        assert geocode("selected address") == []
    with patch.object(services.requests, "get", return_value=response({"bad": True})):
        with pytest.raises(ServiceError):
            geocode("selected address")


def test_network_error_does_not_expose_credentials():
    with patch.object(services.requests, "get", side_effect=requests.Timeout("url?key=SECRET")):
        with pytest.raises(ServiceError) as error:
            street_view("SECRET", Location(40.7, -73.99, "selected"))
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("status", ["ZERO_RESULTS", "NOT_FOUND", "REQUEST_DENIED", "OVER_QUERY_LIMIT"])
def test_no_image_request_without_successful_metadata(status):
    with patch.object(services.requests, "get", return_value=response({"status": status})) as get:
        if status in {"ZERO_RESULTS", "NOT_FOUND"}:
            assert street_view("key", Location(40.7, -73.99, "selected")) is None
        else:
            with pytest.raises(ServiceError):
                street_view("key", Location(40.7, -73.99, "selected"))
    assert get.call_count == 1


def test_no_key_makes_no_request():
    with patch.object(services.requests, "get") as get:
        assert street_view("", Location(40.7, -73.99, "selected")) is None
        get.assert_not_called()


def test_metadata_precedes_image_and_heading_points_toward_building():
    metadata = {"status": "OK", "pano_id": "test-pano", "location": {"lat": 40.6999, "lng": -73.99},
                "date": "2025-01", "copyright": "Google"}
    with patch.object(services.requests, "get", side_effect=[response(metadata), response()]) as get:
        image = street_view("key", Location(40.7, -73.99, "selected"))
    assert get.call_args_list[0].args[0].endswith("/metadata")
    params = get.call_args_list[1].kwargs["params"]
    assert params["pano"] == "test-pano" and params["heading"] == 0
    assert params["return_error_code"] == "true"
    assert image.content == b"image bytes" and image.date == "2025-01"


def test_reject_distant_panorama():
    metadata = {"status": "OK", "pano_id": "far", "location": {"lat": 40.71, "lng": -73.99}}
    with patch.object(services.requests, "get", return_value=response(metadata)) as get:
        assert street_view("key", Location(40.7, -73.99, "selected")) is None
        assert get.call_count == 1
