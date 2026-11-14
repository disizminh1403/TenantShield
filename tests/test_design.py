import pytest

from tenantshield.design import gauge_svg


@pytest.mark.parametrize("probability", [0, 0.041095782071352005, 0.5, 0.9930439591407776, 1])
def test_gauge_uses_continuous_source_probability(probability):
    markup = gauge_svg(probability)
    assert f'stroke-dasharray="{probability * 100:.8f} 100"' in markup
    assert '>0%</text>' in markup and '>100%</text>' in markup
    assert 'role="img"' in markup and 'aria-label=' in markup


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan")])
def test_gauge_rejects_invalid_probability(probability):
    with pytest.raises(ValueError):
        gauge_svg(probability)
