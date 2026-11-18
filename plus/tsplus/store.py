"""Load and validate the precomputed Plus table, and answer comparison questions about it.

Nothing here trains or changes a prediction. The original `PredictedRisk` comes from the
main app CSV; the companion columns come from plus/data/plus_predictions.csv, which is
written offline by plus/pipeline/build_predictions.py.
"""

import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

from tenantshield.data import DataError, load_data, normalize_id


PROBABILITIES = ("ChronicRisk", "RestOfSeasonRisk")
COUNTS = ("SeasonToDate", "SeasonToDateApartments")
REQUIRED = {"BuildingID", "ExpectedComplaints", *PROBABILITIES, *COUNTS}
# Columns whose name carries the season they describe, e.g. Apartments2025 -> ApartmentsLastSeason.
YEARED = {"Apartments": "ApartmentsLastSeason", "BuildingWide": "BuildingWideLastSeason", "OffSeason": "OffSeasonBefore"}
SIZE_BANDS = ((2, "1–2 units"), (5, "3–5 units"), (19, "6–19 units"), (49, "20–49 units"), (math.inf, "50+ units"))
UNKNOWN_SIZE = "Unit count unavailable"
REPORT_KEYS = ("data_through", "deploy_season", "test_season", "chronic_threshold", "backtest")


def season_label(column_or_year: str | int) -> str:
    start = int(re.sub(r"\D", "", str(column_or_year)))
    return f"{start}–{str(start + 1)[-2:]}"


def season_columns(frame: pd.DataFrame) -> list[str]:
    """Columns named Complaints<season start year>, oldest first."""
    return sorted(c for c in frame.columns if re.fullmatch(r"Complaints\d{4}", c))


def load_plus(path: str | Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataError("Cannot read the Plus predictions CSV. Rebuild it with plus/pipeline/build_predictions.py.") from exc
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise DataError(f"Plus predictions CSV is missing columns: {', '.join(sorted(missing))}.")
    frame["BuildingID"] = frame.BuildingID.map(normalize_id)
    if frame.BuildingID.eq("").any() or frame.BuildingID.duplicated().any():
        raise DataError("Plus predictions need exactly one row per BuildingID.")
    for column in frame.columns.drop("BuildingID"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in PROBABILITIES:
        if frame[column].isna().any() or not frame[column].between(0, 1).all():
            raise DataError(f"{column} must be present and between 0 and 1 for every row.")
    for column in ("ExpectedComplaints", *COUNTS):
        if frame[column].isna().any() or frame[column].lt(0).any():
            raise DataError(f"{column} must be present and nonnegative for every row.")
    for column in season_columns(frame):
        # Blank means the building was not yet eligible that season; it is not a zero.
        if frame[column].lt(0).any():
            raise DataError(f"{column} cannot be negative.")
    for prefix, name in YEARED.items():
        matches = [c for c in frame.columns if re.fullmatch(prefix + r"\d{4}", c)]
        frame[name] = frame[matches[-1]] if matches else np.nan
    for column, low, high in (("Latitude", 40.49, 40.75), ("Longitude", -74.06, -73.83)):
        if column not in frame:
            frame[column] = np.nan
        # Out-of-range coordinates are treated as unavailable rather than plotted.
        frame[column] = frame[column].where(frame[column].between(low, high))
    return frame.set_index("BuildingID")


def load_all(base_path: str | Path, plus_path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """Main app data with the Plus columns attached by BuildingID."""
    base, warnings = load_data(base_path)
    plus = load_plus(plus_path)
    frame = base.join(plus, how="left")
    unmatched = int(frame.ChronicRisk.isna().sum())
    if unmatched:
        warnings.append(f"{unmatched:,} buildings have no Plus estimates; rebuild the Plus table for the current CSV.")
    units = frame.LegalClassA if "LegalClassA" in frame else pd.Series(np.nan, index=frame.index)
    frame["SizeBand"] = units.map(size_band)
    frame["Units"] = units.where(units > 0)
    return frame, warnings


def load_report(path: str | Path) -> dict:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DataError("Cannot read the Plus report. Rebuild it with plus/pipeline/build_predictions.py.") from exc
    if not isinstance(report, dict) or any(key not in report for key in REPORT_KEYS):
        raise DataError("The Plus report is incomplete. Rebuild it with plus/pipeline/build_predictions.py.")
    return report


def size_band(units: object) -> str:
    if units is None or pd.isna(units) or units <= 0:
        return UNKNOWN_SIZE
    return next(label for limit, label in SIZE_BANDS if units <= limit)


def valid_zip(value: object) -> bool:
    """The source CSV marks a missing ZIP with text such as NA; only five digits count."""
    return isinstance(value, str) and re.fullmatch(r"\d{5}", value) is not None


def has_plus(row: pd.Series) -> bool:
    return not pd.isna(row.get("ChronicRisk"))


def share_below(values: pd.Series, value: float) -> float:
    """Share of buildings with a strictly lower value, so ties never inflate a rank."""
    values = values.dropna()
    return float(values.lt(value).mean()) if len(values) and not pd.isna(value) else float("nan")


def peer_groups(frame: pd.DataFrame, row: pd.Series) -> list[tuple[str, pd.DataFrame]]:
    groups = [("All scored Brooklyn buildings", frame)]
    zip_code = row.get("Zip")
    if valid_zip(zip_code):
        groups.append((f"ZIP {zip_code}", frame[frame.Zip.eq(zip_code)]))
    if row.SizeBand != UNKNOWN_SIZE:
        groups.append((f"Buildings with {row.SizeBand}", frame[frame.SizeBand.eq(row.SizeBand)]))
    return groups


def comparison(frame: pd.DataFrame, row: pd.Series, column: str) -> list[dict]:
    """Where this building's value sits within each peer group."""
    return [{"group": label, "buildings": len(peers), "median": float(peers[column].median()),
             "share_below": share_below(peers[column], row[column])}
            for label, peers in peer_groups(frame, row)]


def band_for(reliability: list[dict], probability: float) -> dict | None:
    """The backtest score band that contains this probability."""
    for band in reliability:
        if band["low"] <= probability < band["high"] or (probability >= band["high"] >= 1):
            return band
    return None


def count_band(bins: list[dict], expected: float) -> dict | None:
    """The backtest expected-count band that contains this value. `high` is None for the open top band."""
    for band in bins:
        if band["low"] <= expected and (band["high"] is None or expected < band["high"]):
            return band
    return None


def nearby(frame: pd.DataFrame, row: pd.Series, radius_m: float = 250, limit: int = 400) -> pd.DataFrame:
    """Other scored buildings within `radius_m` of this building's tax-lot point, nearest first."""
    if pd.isna(row.get("Latitude")) or pd.isna(row.get("Longitude")):
        return frame.iloc[:0].assign(DistanceM=pd.Series(dtype=float))
    # Equirectangular distance: error is far below a metre at neighbourhood scale.
    north = (frame.Latitude - row.Latitude) * 111_320
    east = (frame.Longitude - row.Longitude) * 111_320 * math.cos(math.radians(row.Latitude))
    distance = np.hypot(north, east)
    mask = distance.le(radius_m) & frame.BuildingID.ne(row.BuildingID)
    return frame[mask].assign(DistanceM=distance[mask].round()).sort_values("DistanceM", kind="stable").head(limit)


def per_100_units(complaints: float, units: float) -> float | None:
    if pd.isna(complaints) or pd.isna(units) or units <= 0:
        return None
    return float(complaints) / float(units) * 100


def area_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per ZIP code, from recorded complaints and the precomputed estimates."""
    last = season_columns(frame)[-1]
    known = frame[frame.Zip.map(valid_zip)]
    grouped = known.groupby("Zip")
    units = grouped.Units.sum()
    summary = pd.DataFrame({
        "Buildings": grouped.size(),
        "ComplaintThisSeasonShare": grouped.SeasonToDate.apply(lambda s: s.gt(0).mean()),
        "ComplaintLastSeasonShare": grouped[last].apply(lambda s: s.gt(0).mean()),
        "ComplaintsPer100Units": grouped[last].sum() / units.where(units > 0) * 100,
        "MedianEstimate": grouped.PredictedRisk.median(),
        "MeanEstimate": grouped.PredictedRisk.mean(),
        "MeanChronicRisk": grouped.ChronicRisk.mean(),
    })
    return summary.sort_values("ComplaintLastSeasonShare", ascending=False)
