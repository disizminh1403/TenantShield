"""Validate source data without changing model predictions."""

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata

import pandas as pd


REQUIRED = {"BuildingID", "BIN", "FullAddress", "PredictedRisk"}
OPTIONAL_NUMERIC = (
    "LegalClassA", "LegalStories", "Construction Year",
    "PastComplaints_Clean", "Complaints2SeasonsAgo_Clean",
    "HasPriorSeasonHistory", "HasTwoSeasonsHistory",
)
MISSING = {"", "na", "nan", "null", "none", "<na>"}


class DataError(ValueError):
    """An actionable input-data problem."""


def normalize_id(value: object) -> str:
    """Accept integer/decimal/scientific CSV identifiers without float rounding."""
    text = str(value).strip()
    if text.lower() in MISSING:
        return ""
    if not re.fullmatch(r"\+?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        raise DataError("Identifiers must be positive whole numbers.")
    try:
        number = Decimal(text)
        if not number.is_finite() or number <= 0 or number > 10**20:
            raise DataError("Identifiers must be positive whole numbers.")
        if number != number.to_integral_value():
            raise DataError("Identifiers must be positive whole numbers.")
        # Preserve leading zeros in already-text integer identifiers.
        return text.lstrip("+") if text.lstrip("+").isdigit() else format(number, ".0f")
    except InvalidOperation as exc:
        raise DataError("Invalid identifier.") from exc


def normalize_address(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).upper()
    text = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", text)
    text = re.sub(r"[^\w\s-]", " ", text)
    aliases = {"ST": "STREET", "AVE": "AVENUE", "AV": "AVENUE",
               "RD": "ROAD", "BLVD": "BOULEVARD", "PL": "PLACE",
               "PKWY": "PARKWAY", "LN": "LANE", "CT": "COURT"}
    return " ".join(aliases.get(word, word) for word in text.split())


def load_data(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataError("Cannot read the data CSV. Check its path, encoding and format.") from exc
    return validate_data(frame)


def validate_data(source: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    missing = REQUIRED - set(source.columns)
    if missing:
        raise DataError(f"CSV is missing required columns: {', '.join(sorted(missing))}.")
    if source.empty:
        raise DataError("CSV contains no buildings.")
    frame = source.copy()
    warnings = []
    for column in ("BuildingID", "BIN"):
        frame[column] = frame[column].map(normalize_id)
    if frame.BuildingID.eq("").any():
        raise DataError("Every row must have a BuildingID.")
    if frame.BuildingID.duplicated().any():
        raise DataError("Duplicate BuildingID values found. Supply one prediction per building.")
    invalid_bin = frame.BIN.ne("") & ~frame.BIN.str.fullmatch(r"\d{7}")
    if invalid_bin.any():
        raise DataError("Nonmissing BIN values must contain seven digits.")
    frame["FullAddress"] = frame.FullAddress.fillna("").astype(str).str.strip()
    missing_address = frame.FullAddress.str.lower().isin(MISSING)
    frame.loc[missing_address, "FullAddress"] = ""
    if missing_address.any():
        warnings.append(f"{int(missing_address.sum()):,} buildings have no address; use BIN lookup.")
    if frame.BIN.eq("").any():
        warnings.append(f"{int(frame.BIN.eq('').sum()):,} buildings have no BIN; use address search.")
    risk = pd.to_numeric(frame.PredictedRisk, errors="coerce")
    if risk.isna().any() or not risk.between(0, 1).all():
        raise DataError("PredictedRisk must be numeric, present and between 0 and 1 for every row.")
    frame["PredictedRisk"] = risk
    for column in OPTIONAL_NUMERIC:
        if column not in frame:
            continue
        raw = frame[column].fillna("").astype(str).str.strip()
        values = pd.to_numeric(raw, errors="coerce")
        invalid = (~raw.str.lower().isin(MISSING)) & (
            values.isna() | values.lt(0) | values.eq(float("inf")) | values.mod(1).ne(0)
        )
        if column.startswith("Has"):
            invalid |= values.notna() & ~values.isin([0, 1])
        if invalid.any():
            warnings.append(f"{int(invalid.sum()):,} invalid {column} values shown as unavailable.")
        frame[column] = values.mask(invalid)
    frame["_address"] = frame.FullAddress.map(normalize_address)
    frame = frame.set_index("BuildingID", drop=False)
    return frame, warnings


def search_buildings(frame: pd.DataFrame, query: str, mode: str = "Address") -> pd.DataFrame:
    query = query.strip()
    if not query:
        return frame.iloc[:0]
    if mode == "BIN":
        try:
            identifier = normalize_id(query)
        except DataError:
            return frame.iloc[:0]
        return frame.loc[frame.BIN.eq(identifier)]
    normalized = normalize_address(query)
    if not normalized:
        return frame.iloc[:0]
    # Literal matching: regex syntax in user input never executes.
    matches = frame.loc[frame._address.str.contains(normalized, regex=False)]
    return matches.assign(_exact=matches._address.eq(normalized)).sort_values(
        ["_exact", "FullAddress", "BIN"], ascending=[False, True, True], kind="stable"
    ).drop(columns="_exact")


def display_number(value: object) -> str:
    if pd.isna(value) or value == "":
        return "Unavailable"
    return f"{float(value):,.0f}"


def historical_count(row: pd.Series, count_column: str, flag_column: str) -> str:
    value = row.get(count_column)
    flag = row.get(flag_column)
    if flag == 0 or value is None or pd.isna(value):
        return "Unavailable"
    if value == 0 and (flag is None or pd.isna(flag)):
        return "0 / unknown"
    return display_number(value)
