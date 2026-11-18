from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tsplus import live
from tenantshield.services import ServiceError

APP = str(Path(__file__).resolve().parents[1] / "app.py")
SEARCH = "FormSubmitter:plus_lookup-Search"
SAMPLE = "FormSubmitter:plus_lookup-Try a sample building"
NO_NETWORK = AssertionError("This interaction must not use the network")


def start() -> AppTest:
    return AppTest.from_file(APP, default_timeout=90).run()


def search(app: AppTest, text: str) -> AppTest:
    app.text_input(key="plus_input").set_value(text)
    app.button(key=SEARCH).click().run()
    return app


def values(app: AppTest) -> dict:
    return {metric.label: metric.value for metric in app.metric}


def test_search_and_profile_work_offline(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    with patch("requests.get", side_effect=NO_NETWORK), patch("requests.Session.request", side_effect=NO_NETWORK):
        app = start()
        assert not app.exception and not app.metric
        search(app, "10 jay st")
        assert not app.exception
        shown = values(app)
        assert shown["At least one recorded complaint"] == "4.1%"          # the original score, unchanged
        assert {"5 or more recorded complaints", "Expected recorded complaints",
                "Chance of at least one more by 31 May", "Recorded complaints since 1 October"} <= set(shown)
        search(app, "jay st")                                              # ambiguous: nothing shown until chosen
        assert app.selectbox(key="plus_choice_Address_jay st").value is None and not app.metric
        search(app, "THIS ADDRESS DOES NOT EXIST")
        assert any("No matching building" in info.value for info in app.info)
        app.radio(key="plus_mode").set_value("BIN").run()
        search(app, "3000002")
        assert values(app)["At least one recorded complaint"] == "4.1%" and not app.exception


def test_sample_building_shows_context_without_safety_labels(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    app = start()
    app.button(key=SAMPLE).click().run()
    assert not app.exception
    assert app.header[0].value == "1035 WASHINGTON AVENUE, BROOKLYN"
    page_text = " ".join([m.value for m in app.markdown] + [c.value for c in app.caption]).lower()
    assert "recorded hpd complaints" in page_text and "not a live feed" in page_text
    for label in ("high risk", "low risk", "unsafe", "safe building"):
        assert label not in page_text
    assert any("Street View unavailable" in caption.value for caption in app.caption)
    assert len(app.checkbox) >= 4                                          # viewing questions


def test_live_records_are_on_demand_and_scoped_to_the_building(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    records = live.LiveRecords(date(2026, 10, 1), (
        live.Complaint(datetime(2026, 11, 7, 8), "No Heat", "Building-wide", "Open"),
        live.Complaint(datetime(2026, 10, 20, 21), "No Hot Water", "Apartment", "Close")), False)
    violation = live.Violation("C", date(2026, 1, 5), "MOCK VIOLATION FOR UI TEST ONLY: PROVIDE HEAT", True)
    app = start()
    with patch("tsplus.live.heat_complaints", return_value=records) as complaints, \
            patch("tsplus.live.open_violations", return_value=([violation], False)) as violations:
        search(app, "20 Jay Street")
        assert complaints.call_count == 0                                  # nothing is fetched until asked
        next(b for b in app.button if b.key and b.key.startswith("live_")).click().run()
        assert complaints.call_count == 1 and violations.call_count == 1
        assert complaints.call_args.args[0] == app.session_state["plus_live"][0]
    assert not app.exception
    assert values(app)["Reported as building-wide"] == "1"
    assert any("Mentioning heat or hot water:** 1" in m.value for m in app.markdown)
    search(app, "25 Jay Street")                                           # never show another building's records
    assert "Reported as building-wide" not in values(app)


def test_live_failure_keeps_the_profile(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    app = start()
    search(app, "185 Plymouth Street")
    with patch("tsplus.live.heat_complaints", side_effect=ServiceError("NYC Open Data could not be reached.")):
        next(b for b in app.button if b.key and b.key.startswith("live_")).click().run()
    assert not app.exception
    assert any("Live records unavailable" in warning.value for warning in app.warning)
    assert "At least one recorded complaint" in values(app)


def test_shortlist_and_other_pages(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    app = start()
    app.button(key=SAMPLE).click().run()
    app.button(key="shortlist_add_388518").click().run()
    assert app.session_state["shortlist"] == ["388518"]
    app.switch_page("pages/Compare_Shortlist.py").run()
    assert not app.exception
    table = app.dataframe[0].value
    assert "1035 WASHINGTON AVENUE, BROOKLYN" in table.columns and len(table) == 12
    app.button(key="remove_388518").click().run()
    assert app.session_state["shortlist"] == [] and any("shortlist is empty" in i.value for i in app.info)
    for page, heading in (("pages/Area_Explorer.py", "Explore Brooklyn by ZIP code"),
                          ("pages/Evidence.py", "Evidence & method")):
        app.switch_page(page).run()
        assert not app.exception and app.title[0].value == heading
    assert any("appear to cover different windows" in warning.value for warning in app.warning)
