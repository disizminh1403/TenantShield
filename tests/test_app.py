from pathlib import Path
from unittest.mock import patch
from io import BytesIO

from PIL import Image
from streamlit.testing.v1 import AppTest

from tenantshield.services import Location, ServiceError, StreetImage


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_search_profile_without_network(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    with patch("tenantshield.services.requests.get", side_effect=AssertionError("Search must remain local")):
        app = AppTest.from_file(str(APP), default_timeout=45).run()
        assert not app.exception
        app.text_input[0].set_value("10 jay st").run()
        assert not app.exception
        assert app.metric[0].value == "4.1%"
        assert any(m.value == "0 / unknown" for m in app.metric)
        assert not app.get("iframe")
        app.text_input[0].set_value("jay st").run()
        assert app.selectbox[0].value is None
        assert not app.metric
        app.text_input[0].set_value("THIS ADDRESS DOES NOT EXIST").run()
        assert any("No matching" in info.value for info in app.info)
        app.radio[0].set_value("BIN").run()
        app.text_input[0].set_value("3000002").run()
        assert app.metric[0].value == "4.1%" and not app.exception


def test_on_demand_location_and_missing_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("10 Jay Street").run()
    location = Location(40.70, -73.99, "MOCK GEOCODE FOR UI TEST ONLY")
    with patch("tenantshield.services.geocode", return_value=[location]) as geocoder:
        app.button[0].click().run()
    assert geocoder.call_count == 1
    assert not app.exception
    assert len(app.get("iframe")) == 1
    assert any("not configured" in info.value for info in app.info)
    app.text_input[0].set_value("25 Jay Street").run()
    assert not app.get("iframe")  # Never show the previous building's location.


def test_geocode_failure_preserves_profile():
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("20 Jay Street").run()
    with patch("tenantshield.services.geocode", side_effect=ServiceError("Network unavailable")):
        app.button[0].click().run()
    assert not app.exception and app.metric
    assert any("Network unavailable" in warning.value for warning in app.warning)


def test_combined_load_and_no_automatic_image_refetch(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("25 Jay Street").run()
    assert not app.exception
    assert app.button[0].label == "Load map & Street View"
    assert any("scored-cohort median" in element.value for element in app.markdown)
    location = Location(40.70, -73.99, "MOCK ADDRESS FOR TEST ONLY")
    output = BytesIO()
    Image.new("RGB", (2, 2), color=(1, 31, 91)).save(output, format="JPEG")
    image = StreetImage(output.getvalue(), "test date", "Google Maps")
    with patch("tenantshield.services.geocode", return_value=[location]) as geocoder, \
            patch("tenantshield.services.street_view", return_value=image) as imagery:
        app.button[0].click().run()
        assert not app.exception and len(app.get("iframe")) == 1
        assert len(app.image) == 1
        assert imagery.call_count == 1 and geocoder.call_count == 1
        app.run()
        assert imagery.call_count == 1  # Rerenders do not spend API quota.
        app.button[0].click().run()
        assert imagery.call_count == 1  # Rapid repeat gesture is throttled.
        assert geocoder.call_count == 1  # Selected address comes from the cache.
        assert any("10 seconds" in info.value for info in app.info)


def test_map_only_opt_out_with_configured_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("3000002")  # Address search remains local.
    app.radio[0].set_value("BIN").run()
    app.text_input[0].set_value("3000002").run()
    app.checkbox[0].uncheck().run()
    with patch("tenantshield.services.geocode", return_value=[Location(40.70, -73.99, "MOCK")]), \
            patch("tenantshield.services.street_view") as imagery:
        app.button[0].click().run()
        assert not app.exception and len(app.get("iframe")) == 1
        imagery.assert_not_called()


def test_street_view_failure_shows_warning_without_broken_image(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("25 Jay Street").run()
    location = Location(40.70, -73.99, "MOCK ADDRESS FOR TEST ONLY")
    with patch("tenantshield.services.geocode", return_value=[location]), \
            patch("tenantshield.services.street_view", side_effect=ServiceError("Google returned an invalid image.")):
        app.button[0].click().run()
    assert not app.exception
    assert len(app.image) == 0
    assert any("invalid image" in warning.value for warning in app.warning)


def test_street_view_render_failure_shows_warning(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("25 Jay Street").run()
    location = Location(40.70, -73.99, "MOCK ADDRESS FOR TEST ONLY")
    image = StreetImage(b"test-only-content", "test date", "Google Maps")
    with patch("tenantshield.services.geocode", return_value=[location]), \
            patch("tenantshield.services.street_view", return_value=image), \
            patch("streamlit.image", side_effect=OSError("test-only render failure")):
        app.button[0].click().run()
    assert not app.exception
    assert len(app.image) == 0
    assert any("could not be displayed" in warning.value for warning in app.warning)


def test_ambiguous_geocoding_requires_selection_before_imagery(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("6005 5 Avenue").run()
    locations = [Location(40.70, -73.99, "MOCK A"), Location(40.71, -73.99, "MOCK B")]
    with patch("tenantshield.services.geocode", return_value=locations), \
            patch("tenantshield.services.street_view") as imagery:
        app.button[0].click().run()
        assert not app.exception
        assert app.selectbox[0].value is None and not app.get("iframe")
        imagery.assert_not_called()
        app.selectbox[0].select(locations[1]).run()
        assert len(app.get("iframe")) == 1
        imagery.assert_not_called()
