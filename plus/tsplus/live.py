"""On-demand NYC Open Data lookups for ONE user-selected building. Server-side only.

These calls are never made in bulk or in the background: each needs an explicit click, and the
caller caches the result. No credential is required; an optional app token only raises limits.
"""

from dataclasses import dataclass
import logging
from datetime import date, datetime

import requests

from tenantshield.services import TIMEOUT, ServiceError

COMPLAINTS_URL = "https://data.cityofnewyork.us/resource/ygpa-z7cr.json"
VIOLATIONS_URL = "https://data.cityofnewyork.us/resource/wvxf-dwi5.json"
HEAT_WORDS = ("HEAT", "HOT WATER")
ROW_LIMIT = 2000


@dataclass(frozen=True)
class Complaint:
    received: datetime
    problem: str          # e.g. NO HEAT, NO HOT WATER
    scope: str            # "Building-wide" or "Apartment"; apartment numbers are deliberately not kept
    status: str


@dataclass(frozen=True)
class Violation:
    violation_class: str  # A (non-hazardous), B (hazardous), C (immediately hazardous), I (order)
    inspected: date | None
    description: str
    heat_related: bool


@dataclass(frozen=True)
class LiveRecords:
    season_start: date
    complaints: tuple[Complaint, ...]
    truncated: bool


def season_start(today: date) -> date:
    """1 October that begins the heating year containing `today` (October through September)."""
    return date(today.year if today.month >= 10 else today.year - 1, 10, 1)


def _rows(url: str, params: dict, token: str = "") -> list[dict]:
    headers = {"User-Agent": "TenantShield-Classroom-MVP/1.0"}
    if token:
        headers["X-App-Token"] = token   # sent from the server only, never to the browser
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT, headers=headers)
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        detail = f" (HTTP {status})" if isinstance(status, int) else ""
        raise ServiceError(f"NYC Open Data rejected the request{detail}.",
                           status_code=status if isinstance(status, int) else None) from None
    except requests.RequestException as exc:
        # Raw request errors can contain the full URL, so only the error type is logged and nothing is shown.
        logging.getLogger(__name__).warning("NYC Open Data request failed: %s", type(exc).__name__)
        raise ServiceError("NYC Open Data could not be reached. Please try again later.") from None
    except ValueError:
        raise ServiceError("NYC Open Data returned an unreadable response.") from None
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ServiceError("NYC Open Data returned an unexpected response.")
    return payload


def _when(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _building(building_id: str) -> str:
    # The identifier is interpolated into a query, so accept digits only.
    if not building_id.isdigit():
        raise ServiceError("Live records need a numeric BuildingID.")
    return building_id


def heat_complaints(building_id: str, today: date, token: str = "") -> LiveRecords:
    """Heat/hot-water complaints for one building since 1 October, newest first, one row per complaint."""
    start = season_start(today)
    rows = _rows(COMPLAINTS_URL, {
        "$select": "complaint_id,received_date,unit_type,problem_code,complaint_status",
        "$where": f"building_id='{_building(building_id)}' AND major_category='HEAT/HOT WATER' "
                  f"AND received_date>='{start.isoformat()}T00:00:00'",
        "$order": "received_date DESC", "$limit": ROW_LIMIT,
    }, token)
    complaints, seen = [], set()
    for row in rows:
        received = _when(row.get("received_date"))
        identifier = row.get("complaint_id")
        if received is None or not identifier or identifier in seen:
            continue   # one complaint can list several problems; count it once
        seen.add(identifier)
        scope = "Building-wide" if row.get("unit_type") == "BUILDING-WIDE" else "Apartment"
        complaints.append(Complaint(received, str(row.get("problem_code", "Not stated")).title(), scope,
                                    str(row.get("complaint_status", "Not stated")).title()))
    return LiveRecords(start, tuple(complaints), len(rows) >= ROW_LIMIT)


def open_violations(building_id: str, token: str = "") -> tuple[list[Violation], bool]:
    """Currently open HPD violations for one building, newest inspection first."""
    rows = _rows(VIOLATIONS_URL, {
        "$select": "class,inspectiondate,novdescription",
        "$where": f"buildingid='{_building(building_id)}' AND violationstatus='Open'",
        "$order": "inspectiondate DESC", "$limit": ROW_LIMIT,
    }, token)
    violations = []
    for row in rows:
        description = " ".join(str(row.get("novdescription", "")).split())
        inspected = _when(row.get("inspectiondate"))
        violations.append(Violation(str(row.get("class", "?")).upper()[:1] or "?",
                                    inspected.date() if inspected else None, description,
                                    any(word in description.upper() for word in HEAT_WORDS)))
    return violations, len(rows) >= ROW_LIMIT
