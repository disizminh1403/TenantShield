"""Small Altair charts. One y-axis each, thin rounded bars, hover tooltips, and a table view nearby.

The two series colours were checked with a colour-vision-deficiency validator against a light
surface; single-series charts use the first one.
"""

import altair as alt
import pandas as pd

SERIES_1, SERIES_2 = "#2a78d6", "#eb6834"
INK, GRID = "#52514e", "#e6e9ee"


def _style(chart: alt.Chart, height: int = 240) -> alt.Chart:
    return (chart.properties(height=height)
            .configure_axis(labelColor=INK, titleColor=INK, gridColor=GRID, domainColor=GRID, tickColor=GRID,
                            labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelColor=INK, title=None, orient="top", labelFontSize=12)
            .configure_view(stroke=None))


def bars(data: pd.DataFrame, category: str, value: str, value_title: str, percent: bool = False,
         horizontal: bool = False, height: int = 240, decimals: int = 0) -> alt.Chart:
    """Single-series bar chart; `data` rows are drawn in the order given."""
    fmt = ".1%" if percent else f",.{decimals}f"
    position = alt.X if not horizontal else alt.Y
    measure = alt.Y if not horizontal else alt.X
    corners = dict(cornerRadiusTopLeft=4, cornerRadiusTopRight=4) if not horizontal else \
        dict(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
    chart = alt.Chart(data).mark_bar(color=SERIES_1, **corners).encode(
        position(f"{category}:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelLimit=340),
                 scale=alt.Scale(paddingInner=.35)),
        measure(f"{value}:Q", title=value_title, axis=alt.Axis(format="%" if percent else "~g", tickMinStep=.01 if percent or decimals else 1)),
        tooltip=[alt.Tooltip(f"{category}:N", title=" "), alt.Tooltip(f"{value}:Q", title=value_title, format=fmt)],
    )
    return _style(chart, height)


def paired_bars(data: pd.DataFrame, category: str, first: tuple[str, str], second: tuple[str, str],
                value_title: str, height: int = 260) -> alt.Chart:
    """Two series on one shared percentage axis, side by side within each category."""
    long = data.melt(id_vars=[category], value_vars=[first[0], second[0]], var_name="Series", value_name="Value")
    long["Series"] = long.Series.map({first[0]: first[1], second[0]: second[1]})
    order = [first[1], second[1]]
    chart = alt.Chart(long).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        alt.X(f"{category}:N", sort=None, title="Estimate band", axis=alt.Axis(labelAngle=0),
              scale=alt.Scale(paddingInner=.25)),
        alt.XOffset("Series:N", sort=order, scale=alt.Scale(paddingInner=.12)),
        alt.Y("Value:Q", title=value_title, axis=alt.Axis(format="%")),
        alt.Color("Series:N", sort=order, scale=alt.Scale(domain=order, range=[SERIES_1, SERIES_2])),
        tooltip=[alt.Tooltip(f"{category}:N", title="Estimate band"), alt.Tooltip("Series:N", title=" "),
                 alt.Tooltip("Value:Q", title=value_title, format=".1%")],
    )
    return _style(chart, height)
