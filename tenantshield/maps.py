"""OpenStreetMap's interactive embed keeps tile attribution and browser caching intact."""

from urllib.parse import urlencode

from tenantshield.services import Location


def map_urls(location: Location) -> tuple[str, str]:
    lat, lon = location.latitude, location.longitude
    params = urlencode({"bbox": f"{lon-.003},{lat-.002},{lon+.003},{lat+.002}",
                        "layer": "mapnik", "marker": f"{lat},{lon}"})
    embed = "https://www.openstreetmap.org/export/embed.html?" + params
    full = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
    return embed, full
