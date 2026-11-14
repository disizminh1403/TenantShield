from pathlib import Path
from unittest.mock import patch
from io import BytesIO

from PIL import Image
import pytest
from streamlit.errors import StreamlitAPIException
from streamlit.testing.v1 import AppTest

from tenantshield.services import Location, ServiceError, StreetImage


APP = Path(__file__).resolve().parents[1] / "app.py"


def search(app, query):
    app.text_input[0].set_value(query)
    app.button(key="FormSubmitter:building_lookup-Search").click().run()
    return app


def test_search_profile_without_network(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    with patch("tenantshield.services.requests.get", side_effect=AssertionError("Search must remain local")):
        app = AppTest.from_file(str(APP), default_timeout=45).run()
        assert not app.exception
        search(app, "10 jay st")
        assert not app.exception
        assert any("4.1% estimated chance" in item.value for item in app.markdown)
        assert any(m.value == "Record status uncertain" for m in app.metric)
        assert not app.get("iframe")
        search(app, "jay st")
        assert app.selectbox[0].value is None
        assert not app.metric
        search(app, "THIS ADDRESS DOES NOT EXIST")
        assert any("No matching" in info.value for info in app.info)
        app.radio[0].set_value("BIN").run()
        search(app, "3000002")
        assert any("4.1% estimated chance" in item.value for item in app.markdown) and not app.exception


def test_on_demand_location_and_missing_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    search(app, "10 Jay Street")
    location = Location(40.70, -73.99, "MOCK GEOCODE FOR UI TEST ONLY")
    with patch("tenantshield.services.geocode", return_value=[location]) as geocoder:
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
    assert geocoder.call_count == 1
    assert not app.exception
    assert len(app.get("iframe")) == 1
    assert any("not configured" in info.value for info in app.info)
    search(app, "25 Jay Street")
    assert not app.get("iframe")  # Never show the previous building's location.


def test_geocode_failure_preserves_profile():
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    search(app, "20 Jay Street")
    with patch("tenantshield.services.geocode", side_effect=ServiceError("Network unavailable")):
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
    assert not app.exception and app.metric
    assert any("Network unavailable" in warning.value for warning in app.warning)


@pytest.mark.parametrize("embed_fails", [False, True])
def test_combined_load_and_no_automatic_image_refetch(monkeypatch, embed_fails):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    search(app, "1035 Washington Avenue" if embed_fails else "25 Jay Street")
    assert not app.exception
    assert next(button for button in app.button if button.key and button.key.startswith("locate_")).label == "Load map & Street View"
    assert any("2.9% median estimate" in element.value for element in app.markdown)
    location = Location(40.70, -73.99, "MOCK ADDRESS FOR TEST ONLY")
    output = BytesIO()
    Image.new("RGB", (2, 2), color=(1, 31, 91)).save(output, format="JPEG")
    image = StreetImage(output.getvalue(), "test date", "Google Maps")
    if embed_fails:
        def fail_embed(*args, **kwargs):
            raise StreamlitAPIException("Test embed failure")

        monkeypatch.setattr("streamlit.components.v1.iframe", fail_embed)
    with patch("tenantshield.services.geocode", return_value=[location]) as geocoder, \
            patch("tenantshield.services.street_view", return_value=image) as imagery:
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
        assert not app.exception
        assert len(app.get("iframe")) == int(not embed_fails)
        assert any("Open larger map" in item.value for item in app.markdown)
        assert any("Map preview unavailable" in item.value for item in app.info) == embed_fails
        assert len(app.image) == 1
        assert imagery.call_count == 1 and geocoder.call_count == 1
        app.run()
        assert imagery.call_count == 1  # Rerenders do not spend API quota.
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
        assert imagery.call_count == 1  # Rapid repeat gesture is throttled.
        assert geocoder.call_count == 1  # Selected address comes from the cache.
        assert any("10 seconds" in info.value for info in app.info)


def test_map_only_opt_out_with_configured_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    app.text_input[0].set_value("3000002")  # Address search remains local.
    app.radio[0].set_value("BIN").run()
    search(app, "3000002")
    app.checkbox[0].uncheck().run()
    with patch("tenantshield.services.geocode", return_value=[Location(40.70, -73.99, "MOCK")]), \
            patch("tenantshield.services.street_view") as imagery:
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
        assert not app.exception and len(app.get("iframe")) == 1
        imagery.assert_not_called()


def test_street_view_failure_shows_warning_without_broken_image(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    search(app, "25 Jay Street")
    location = Location(40.70, -73.99, "MOCK ADDRESS FOR TEST ONLY")
    with patch("tenantshield.services.geocode", return_value=[location]), \
            patch("tenantshield.services.street_view", side_effect=ServiceError("Google returned an invalid image.")):
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
    assert not app.exception
    assert len(app.image) == 0
    assert any("invalid image" in warning.value for warning in app.warning)


def test_street_view_render_failure_shows_warning(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    search(app, "25 Jay Street")
    location = Location(40.70, -73.99, "MOCK ADDRESS FOR TEST ONLY")
    image = StreetImage(b"test-only-content", "test date", "Google Maps")
    with patch("tenantshield.services.geocode", return_value=[location]), \
            patch("tenantshield.services.street_view", return_value=image), \
            patch("streamlit.image", side_effect=OSError("test-only render failure")):
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
    assert not app.exception
    assert len(app.image) == 0
    assert any("could not be displayed" in warning.value for warning in app.warning)


def test_ambiguous_geocoding_requires_selection_before_imagery(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-key")
    app = AppTest.from_file(str(APP), default_timeout=45).run()
    search(app, "6005 5 Avenue")
    locations = [Location(40.70, -73.99, "MOCK A"), Location(40.71, -73.99, "MOCK B")]
    with patch("tenantshield.services.geocode", return_value=locations), \
            patch("tenantshield.services.street_view") as imagery:
        next(button for button in app.button if button.key and button.key.startswith("locate_")).click().run()
        assert not app.exception
        assert app.selectbox[0].value is None and not app.get("iframe")
        imagery.assert_not_called()
        app.selectbox[0].select(locations[1]).run()
        assert len(app.get("iframe")) == 1
        imagery.assert_not_called()


def test_sample_from_bin_mode_and_no_match(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    with patch("tenantshield.services.requests.get", side_effect=AssertionError("Sample must remain local")):
        app = AppTest.from_file(str(APP), default_timeout=45).run()
        assert app.title[0].value == "Check a building’s heating history before you rent."
        assert not any("#complaint-history" in item.value for item in app.markdown)
        app.radio[0].set_value("BIN").run()
        app.button(key="FormSubmitter:building_lookup-Try a sample building").click().run()
        assert app.radio[0].value == "Address"
        assert any(h.value == "1035 WASHINGTON AVENUE, BROOKLYN" for h in app.header)
        assert any("BIN 3029731" in item.value for item in app.markdown)
        assert any("97.9% estimated chance" in item.value for item in app.markdown)
        assert any("2.9% median estimate" in item.value for item in app.markdown)
        assert {metric.label: metric.value for metric in app.metric}["2025–26 season"] == "14"
        assert {metric.label: metric.value for metric in app.metric}["2024–25 season"] == "7"
        search(app, "")
        assert not app.metric
        search(app, "THIS ADDRESS DOES NOT EXIST")
        app.button(key="sample_recovery").click().run()
        assert any(h.value == "1035 WASHINGTON AVENUE, BROOKLYN" for h in app.header)
        assert not app.exception
