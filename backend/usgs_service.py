
"""
USGS Earthquake Feed Service
Fetches recent earthquake events from the USGS FDSNWS API.
India subcontinent bounding box: lat 5-37, lon 62-100
"""

import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
REQUEST_TIMEOUT = 15

INDIA_MINLAT =  5.0
INDIA_MAXLAT = 37.0
INDIA_MINLON = 62.0
INDIA_MAXLON = 100.0


def fetch_recent_earthquakes(days=7, min_mag=2.5, india_only=False):
    """
    Fetch earthquakes from USGS.
    Returns list of {lat, lon, depth, mag, time, place}.
    Raises requests.RequestException on failure.
    """
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "format":       "geojson",
        "starttime":    start,
        "minmagnitude": min_mag,
        "orderby":      "time",
        "limit":        2000,
    }
    if india_only:
        params.update({
            "minlatitude":  INDIA_MINLAT,
            "maxlatitude":  INDIA_MAXLAT,
            "minlongitude": INDIA_MINLON,
            "maxlongitude": INDIA_MAXLON,
        })

    logger.info("Fetching USGS: days=%d min_mag=%s india_only=%s", days, min_mag, india_only)
    r = requests.get(USGS_URL, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    result = []
    for f in data.get("features", []):
        coords = f["geometry"]["coordinates"]
        props  = f["properties"]
        mag    = props.get("mag")
        if mag is None:
            continue
        result.append({
            "lat":   coords[1],
            "lon":   coords[0],
            "depth": coords[2],
            "mag":   mag,
            "time":  props.get("time"),
            "place": props.get("place", ""),
        })

    logger.info("Fetched %d earthquakes", len(result))
    return result
