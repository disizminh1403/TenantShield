"""Server-only requests. Never return request URLs or raw provider errors to the UI."""

from dataclasses import dataclass
import math
import threading
import time

import requests


TIMEOUT = (5, 15)
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
STREET_VIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
_census_lock = threading.Lock()
_last_census_call = 0.0


class ServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    address: str


@dataclass(frozen=True)
class StreetImage:
    content: bytes
    date: str
    copyright: str


def _get(url: str, params: dict) -> requests.Response:
    try:
        response = requests.get(
            url, params=params, timeout=TIMEOUT,
            headers={"User-Agent": "TenantShield-Classroom-MVP/1.0"},
        )
        response.raise_for_status()
        return response
    except requests.RequestException:
        # Requests exceptions often contain the complete URL, including the key.
        raise ServiceError("The location service is unavailable. Please try again later.") from None


def _json(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        raise ServiceError("The location service returned an unreadable response.") from None
    if not isinstance(payload, dict):
        raise ServiceError("The location service returned an unexpected response.")
    return payload


def geocode(address: str) -> list[Location]:
    """Only call with a selected CSV address. Census uses address-range interpolation."""
    global _last_census_call
    if not address.strip():
        return []
    # Modest single-process classroom traffic; cached by the caller as well.
    with _census_lock:
        time.sleep(max(0, 1.0 - (time.monotonic() - _last_census_call)))
        try:
            payload = _json(_get(CENSUS_URL, {
                "address": address, "benchmark": "Public_AR_Current", "format": "json",
            }))
        finally:
            _last_census_call = time.monotonic()
    try:
        matches = payload["result"]["addressMatches"]
        if not isinstance(matches, list):
            raise TypeError
        locations = []
        for match in matches:
            lat, lon = float(match["coordinates"]["y"]), float(match["coordinates"]["x"])
            # A coarse sanity bound, not a claim to validate borough boundaries.
            if 40.49 <= lat <= 40.75 and -74.06 <= lon <= -73.83:
                locations.append(Location(lat, lon, str(match["matchedAddress"])))
        return locations
    except (KeyError, ValueError, TypeError, OverflowError):
        raise ServiceError("The geocoder returned an unexpected response.") from None


def _bearing(start: Location, end: Location) -> float:
    lat1, lat2 = math.radians(start.latitude), math.radians(end.latitude)
    delta = math.radians(end.longitude - start.longitude)
    return math.degrees(math.atan2(
        math.sin(delta) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta),
    )) % 360


def street_view(key: str, location: Location) -> StreetImage | None:
    if not key:
        return None
    metadata = _json(_get(STREET_VIEW_URL + "/metadata", {
        "key": key, "location": f"{location.latitude},{location.longitude}",
        "radius": 50, "source": "outdoor",
    }))
    status = metadata.get("status")
    if status in {"ZERO_RESULTS", "NOT_FOUND"}:
        return None
    if status != "OK":
        raise ServiceError("Street View unavailable. Check API access, billing and quota in Google Cloud.")
    try:
        pano = metadata["pano_id"]
        point = metadata["location"]
        camera = Location(float(point["lat"]), float(point["lng"]), "")
        if not pano or not all(math.isfinite(v) for v in (camera.latitude, camera.longitude)):
            raise ValueError
        # Reject distant panoramas even if a provider unexpectedly ignores radius.
        distance = math.hypot((camera.latitude - location.latitude) * 111_320,
                              (camera.longitude - location.longitude) * 84_400)
        if distance > 60:
            return None
    except (KeyError, TypeError, ValueError):
        raise ServiceError("Street View unavailable: incomplete image metadata.") from None
    response = _get(STREET_VIEW_URL, {
        "key": key, "pano": pano, "size": "640x400", "fov": 80, "pitch": 0,
        "heading": round(_bearing(camera, location), 1), "return_error_code": "true",
    })
    if not response.headers.get("Content-Type", "").lower().startswith("image/"):
        raise ServiceError("Street View unavailable: the service did not return an image.")
    return StreetImage(response.content, str(metadata.get("date", "Date unavailable")),
                       str(metadata.get("copyright", "Google Maps")))
