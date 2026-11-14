from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tenantshield.methodology import capture_chart


ROOT = Path(__file__).resolve().parents[1]


def test_methodology_navigation_metrics_and_return_to_lookup(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    with patch("tenantshield.services.requests.get", side_effect=AssertionError("Navigation must not call an API")):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
        assert not app.exception
        assert any(link.label == "How TenantShield Works" for link in app.get("page_link"))
        app.switch_page("pages/How_TenantShield_Works.py").run()
        assert not app.exception
        assert app.title[0].value == "How TenantShield Works"
        assert {metric.label: metric.value for metric in app.metric} == {
            "ROC-AUC": "0.836", "PR-AUC": "0.592", "Log Loss": "0.219", "Brier Score": "0.0585",
            "Top-decile recall": "56.3%", "Top-decile precision": "55.4%", "Positive outcome prevalence": "9.84%",
        }
        prose = " ".join(item.value for item in app.markdown)
        assert "2022–23 through 2024–25" in prose
        assert "2022–23 through 2025–26" in prose
        assert "Violation features were excluded" in prose
        assert "not a reported random-selection experiment" in " ".join(item.value for item in app.caption)
        app.switch_page("app.py").run()
        app.text_input[0].set_value("10 Jay St").run()
        assert not app.exception and app.metric[0].value == "4.1%"


def test_capture_chart_denominator_scale_and_reported_values():
    chart = capture_chart()
    assert 'width:56.3%' in chart and 'width:10%' in chart
    assert '>0%</span>' in chart and '>100%</span>' in chart
    assert "complaint-positive test buildings" in chart
    assert "expected" in chart and "56.3%" in chart
