"""
Cyclone Service — Phase 1 stub with synthetic India data.
Phase 3 will integrate IMD Best Track data and INCOIS advisories.

IMD Cyclone Categories (Indian Ocean scale):
  CS  — Cyclonic Storm:           89 - 117 km/h
  SCS — Severe Cyclonic Storm:   118 - 167 km/h
  VSCS— Very Severe Cyclonic:    168 - 221 km/h
  ESCS— Extremely Severe:        222 - 279 km/h
  SuCS— Super Cyclonic Storm:    ≥280 km/h
"""

import random
import logging
import datetime
import math

logger = logging.getLogger(__name__)

IMD_CATEGORIES = [
    {"code": "CS",   "label": "Cyclonic Storm",            "wind_min":  89, "wind_max": 117, "color": "#EF9F27"},
    {"code": "SCS",  "label": "Severe Cyclonic Storm",     "wind_min": 118, "wind_max": 167, "color": "#E24B4A"},
    {"code": "VSCS", "label": "Very Severe Cyclonic Storm","wind_min": 168, "wind_max": 221, "color": "#A32D2D"},
    {"code": "ESCS", "label": "Extremely Severe Cyclonic", "wind_min": 222, "wind_max": 279, "color": "#793030"},
    {"code": "SuCS", "label": "Super Cyclonic Storm",      "wind_min": 280, "wind_max": 999, "color": "#4a0a0a"},
]

# Indian coastline segments at risk per cyclone origin
COASTAL_RISK_ZONES = {
    "BoB": ["Odisha", "West Bengal", "Andhra Pradesh", "Tamil Nadu"],
    "AS":  ["Gujarat", "Maharashtra", "Goa", "Kerala"],
    "Andaman": ["Andaman & Nicobar", "Andhra Pradesh"],
}


def _imd_category(wind_kmh):
    for cat in IMD_CATEGORIES:
        if cat["wind_min"] <= wind_kmh <= cat["wind_max"]:
            return cat
    return {"code": "?", "label": "Unknown", "wind_min": 0, "wind_max": 0, "color": "#888"}


def _spiral_track(origin_lat, origin_lon, basin, steps=8):
    """
    Simulate a realistic recurving track.
    Bay of Bengal systems typically recurve NW then N.
    Arabian Sea systems move NNW or W.
    """
    track = []
    lat, lon = origin_lat, origin_lon

    for i in range(steps):
        track.append({
            "lat":  round(lat, 2),
            "lon":  round(lon, 2),
            "hour": i * 6,
        })
        if basin == "BoB":
            lat += random.uniform(0.4, 1.0)
            lon -= random.uniform(0.1, 0.6)
        elif basin == "AS":
            lat += random.uniform(0.3, 0.8)
            lon -= random.uniform(0.4, 1.0)
        else:
            lat += random.uniform(0.5, 1.2)
            lon -= random.uniform(0.2, 0.5)

    return track


def get_active_cyclones():
    """
    Returns currently active cyclone systems.
    Synthetic for Phase 1; replaced by IMD Best Track in Phase 3.
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    month = datetime.datetime.utcnow().month

    # Peak cyclone season: Oct–Dec (BoB) and May–Jun (AS)
    prob = 0.7 if month in (10, 11, 12, 5, 6) else 0.3
    count = 1 if random.random() < prob else 0

    cyclones = []
    for i in range(count):
        basin = random.choice(["BoB", "AS"])
        wind  = random.randint(89, 200)
        cat   = _imd_category(wind)

        if basin == "BoB":
            lat = round(random.uniform(8, 18), 2)
            lon = round(random.uniform(82, 95), 2)
        else:
            lat = round(random.uniform(10, 22), 2)
            lon = round(random.uniform(62, 75), 2)

        pressure  = round(1010 - (wind / 5) * 1.2)
        zones     = COASTAL_RISK_ZONES.get(basin, [])
        landfall  = random.choice(zones) if zones else "Unknown"
        eta_hours = random.randint(12, 72)

        cyclones.append({
            "id":            f"CY-{datetime.datetime.utcnow().year}-{i+1:02d}",
            "name":          f"Cyclone {'MALA' if i == 0 else 'ASNA'}",
            "category_code": cat["code"],
            "category":      cat["label"],
            "color":         cat["color"],
            "basin":         basin,
            "lat":           lat,
            "lon":           lon,
            "wind_kmh":      wind,
            "pressure_hpa":  pressure,
            "movement":      f"NNW at {random.randint(10,20)} km/h",
            "track":         _spiral_track(lat, lon, basin),
            "landfall_zone": landfall,
            "eta_hours":     eta_hours,
            "source":        "synthetic",
            "updated_at":    now,
        })

    return cyclones


def predict_cyclone_risk(lat, lon):
    """
    Predict cyclone risk probability for a given lat/lon.
    Based on climatological frequency map for Indian coasts.
    """
    month = datetime.datetime.utcnow().month

    # Climatological cyclone frequency grid for Indian region
    bob_centre = (14.0, 88.0)
    as_centre  = (16.0, 68.0)

    from geo_utils import haversine
    dist_bob = haversine(lat, lon, *bob_centre)
    dist_as  = haversine(lat, lon, *as_centre)
    dist_min = min(dist_bob, dist_as)

    seasonal = 1.5 if month in (10, 11, 12, 5, 6) else 0.5
    base     = max(0.0, 1.0 - dist_min / 1500.0) * seasonal
    prob     = round(min(base, 0.95), 2)

    if prob > 0.6:
        level = "High"
    elif prob > 0.3:
        level = "Moderate"
    else:
        level = "Low"

    return {
        "risk_level":  level,
        "probability": prob,
        "dist_to_bob": round(dist_bob),
        "dist_to_as":  round(dist_as),
        "source":      "synthetic",
    }
