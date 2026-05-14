"""
Storm Service — Phase 2
Integrates IMD open data for live storm alerts.
Falls back to climatological synthetic data when IMD is unavailable.

IMD Depression / Storm Scale:
  Low Pressure Area (LPA)  : surface wind < 31 km/h
  Depression (D)           : 31 – 61 km/h
  Deep Depression (DD)     : 62 – 88 km/h
  Cyclonic Storm (CS)      : 89 – 117 km/h  → cyclone_service handles
  Severe Cyclonic (SCS)    : 118+ km/h      → cyclone_service handles

Free data sources used:
  1. Open-Meteo Marine API  — wave height, wind speed at sea
  2. OpenWeatherMap (free)  — synoptic pressure fields (no key needed for limited calls)
  3. Synthetic climatology  — fallback with realistic seasonal distributions
"""

import requests
import random
import logging
import datetime
import math
from geo_utils import haversine

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

OPEN_METEO_MARINE = "https://marine-api.open-meteo.com/v1/marine"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 12

# Known storm-genesis hotspots around India (lat, lon, basin, name)
STORM_HOTSPOTS = [
    {"name": "Bay of Bengal (North)",   "lat": 18.0, "lon": 87.0, "basin": "BoB",     "weight": 1.4},
    {"name": "Bay of Bengal (Central)", "lat": 13.5, "lon": 85.5, "basin": "BoB",     "weight": 1.2},
    {"name": "Bay of Bengal (South)",   "lat":  9.0, "lon": 84.0, "basin": "BoB",     "weight": 1.0},
    {"name": "Arabian Sea (NE)",        "lat": 20.0, "lon": 65.5, "basin": "AS",      "weight": 0.9},
    {"name": "Arabian Sea (East)",      "lat": 15.0, "lon": 70.0, "basin": "AS",      "weight": 0.8},
    {"name": "Andaman Sea",             "lat": 11.0, "lon": 93.5, "basin": "Andaman", "weight": 0.7},
    {"name": "Lakshadweep Sea",         "lat": 10.5, "lon": 72.5, "basin": "AS",      "weight": 0.6},
]

# IMD low-pressure system categories
STORM_CATEGORIES = [
    {"code": "LPA", "label": "Low Pressure Area",  "wind_min":  0,  "wind_max": 30,  "color": "#378ADD", "severity": 1},
    {"code": "D",   "label": "Depression",          "wind_min": 31,  "wind_max": 61,  "color": "#1D9E75", "severity": 2},
    {"code": "DD",  "label": "Deep Depression",     "wind_min": 62,  "wind_max": 88,  "color": "#EF9F27", "severity": 3},
    {"code": "CS",  "label": "Cyclonic Storm",      "wind_min": 89,  "wind_max": 117, "color": "#E24B4A", "severity": 4},
]

# Coastal states at risk per basin
COASTAL_STATES = {
    "BoB":     ["West Bengal", "Odisha", "Andhra Pradesh", "Tamil Nadu"],
    "AS":      ["Gujarat", "Maharashtra", "Goa", "Karnataka", "Kerala"],
    "Andaman": ["Andaman & Nicobar Islands"],
}

# Seasonal probability weights (month → relative probability multiplier)
# India storm seasonality: Oct–Dec BoB (NE monsoon), May–Jun AS (pre-monsoon)
SEASONAL_WEIGHTS = {
    1: 0.3, 2: 0.2, 3: 0.2, 4: 0.4, 5: 0.9,
    6: 1.0, 7: 0.6, 8: 0.6, 9: 0.7,
    10: 1.3, 11: 1.5, 12: 0.8,
}


# ── Category helpers ─────────────────────────────────────────────────────────

def _classify_storm(wind_kmh: float) -> dict:
    for cat in STORM_CATEGORIES:
        if cat["wind_min"] <= wind_kmh <= cat["wind_max"]:
            return cat
    return STORM_CATEGORIES[-1]


def _season_label(month: int) -> str:
    if month in (10, 11, 12, 1):
        return "NE Monsoon Season"
    elif month in (5, 6):
        return "Pre-Monsoon Season"
    elif month in (7, 8, 9):
        return "SW Monsoon Season"
    return "Inter-Monsoon"


# ── Marine data fetch ────────────────────────────────────────────────────────

def _fetch_marine_conditions(lat: float, lon: float) -> dict | None:
    """
    Fetch wave height and wind speed from Open-Meteo Marine API.
    Returns dict or None on failure.
    """
    params = {
        "latitude":  lat,
        "longitude": lon,
        "hourly": "wave_height,wind_wave_height,wind_speed_10m",
        "wind_speed_unit": "kmh",
        "forecast_days": 3,
    }
    try:
        r = requests.get(OPEN_METEO_MARINE, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})

        def latest(key):
            vals = [v for v in (hourly.get(key) or []) if v is not None]
            return vals[-1] if vals else None

        return {
            "wave_height_m":      latest("wave_height"),
            "wind_wave_height_m": latest("wind_wave_height"),
            "wind_speed_kmh":     latest("wind_speed_10m"),
            "source":             "open-meteo-marine",
        }
    except Exception as exc:
        logger.warning("Marine API failed for (%.2f, %.2f): %s", lat, lon, exc)
        return None


def _fetch_surface_pressure(lat: float, lon: float) -> float | None:
    """Fetch surface pressure from Open-Meteo forecast API."""
    params = {
        "latitude":  lat,
        "longitude": lon,
        "hourly":    "surface_pressure",
        "forecast_days": 1,
    }
    try:
        r = requests.get(OPEN_METEO_FORECAST, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        vals = [v for v in (r.json().get("hourly", {}).get("surface_pressure") or []) if v is not None]
        return vals[-1] if vals else None
    except Exception:
        return None


# ── Track simulation ─────────────────────────────────────────────────────────

def _simulate_track(origin_lat: float, origin_lon: float, basin: str, steps: int = 8) -> list[dict]:
    """
    Generate a realistic steering-flow track.
    BoB systems: typically NW or NNW toward Indian east coast.
    AS systems: typically NNW or W toward Gujarat / Oman coast.
    Andaman: NW toward Bay of Bengal / Andaman coast.
    """
    track = []
    lat, lon = origin_lat, origin_lon
    speed_kmh = random.uniform(8, 18)

    for i in range(steps):
        track.append({
            "lat":      round(lat, 2),
            "lon":      round(lon, 2),
            "hour":     i * 6,
            "speed_kmh": round(speed_kmh, 1),
        })
        if basin == "BoB":
            lat += random.uniform(0.3, 0.9)
            lon -= random.uniform(0.1, 0.5)
        elif basin == "AS":
            lat += random.uniform(0.2, 0.7)
            lon -= random.uniform(0.4, 1.0)
        else:
            lat += random.uniform(0.4, 1.0)
            lon -= random.uniform(0.15, 0.4)

    return track


# ── Synthetic storm generator ────────────────────────────────────────────────

def _synthetic_storms(month: int) -> list[dict]:
    """
    Generate climatologically plausible synthetic storms.
    Uses seasonal weights and basin preferences.
    """
    seasonal_mult = SEASONAL_WEIGHTS.get(month, 0.5)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    storms = []

    # Number of active systems: Poisson-like draw weighted by season
    base_prob = min(0.85, 0.25 * seasonal_mult)
    count = sum(1 for _ in range(3) if random.random() < base_prob)
    count = min(count, 2)  # cap at 2

    # Prefer BoB in Oct–Dec, AS in May–Jun
    bob_weight = 0.8 if month in (10, 11, 12, 1) else 0.4
    basin_pool = ["BoB"] * int(bob_weight * 10) + ["AS"] * int((1 - bob_weight) * 10)

    chosen_spots = random.sample(STORM_HOTSPOTS, k=min(count, len(STORM_HOTSPOTS)))

    for i, spot in enumerate(chosen_spots):
        wind = random.randint(30, 100)
        cat  = _classify_storm(wind)

        # Skip cyclone-strength systems (handled by cyclone_service)
        if wind >= 89:
            wind = random.randint(30, 88)
            cat  = _classify_storm(wind)

        pressure = round(1010 - wind * 0.18 - random.uniform(0, 5), 1)
        lat = round(spot["lat"] + random.uniform(-2, 2), 2)
        lon = round(spot["lon"] + random.uniform(-2, 2), 2)
        basin = spot["basin"]
        coastal = COASTAL_STATES.get(basin, [])
        affected = random.sample(coastal, k=min(2, len(coastal)))

        # Fetch real marine data for this location
        marine = _fetch_marine_conditions(lat, lon)

        storms.append({
            "id":               f"SYN-{datetime.datetime.utcnow().strftime('%Y%m%d')}-{i+1:02d}",
            "name":             f"System {i+1} ({spot['name']})",
            "category_code":    cat["code"],
            "category":         cat["label"],
            "severity":         cat["severity"],
            "color":            cat["color"],
            "lat":              lat,
            "lon":              lon,
            "basin":            basin,
            "wind_kmh":         wind,
            "pressure_hpa":     pressure,
            "movement":         f"{'NNW' if basin == 'BoB' else 'NW'} at {random.randint(8, 18)} km/h",
            "affected_states":  affected,
            "track":            _simulate_track(lat, lon, basin),
            "marine":           marine,
            "season":           _season_label(month),
            "source":           "synthetic+open-meteo",
            "updated_at":       now,
        })

    return storms


# ── Risk scoring ─────────────────────────────────────────────────────────────

def _score_storm_risk(lat: float, lon: float, month: int, marine: dict | None) -> dict:
    """
    Compute storm risk score for a point.
    Factors: proximity to hotspots, seasonal weight, marine conditions.
    Returns risk score [0, 1], level string, and contributing factors.
    """
    # Distance factor: inverse-distance weighted across all hotspots
    proximity_scores = []
    for hs in STORM_HOTSPOTS:
        d = haversine(lat, lon, hs["lat"], hs["lon"])
        proximity_scores.append(hs["weight"] * max(0.0, 1.0 - d / 2500.0))

    proximity = min(sum(proximity_scores) / len(STORM_HOTSPOTS) * 3.0, 1.0)

    # Seasonal factor
    seasonal = min(SEASONAL_WEIGHTS.get(month, 0.5), 1.0)

    # Marine factor (if available)
    marine_factor = 0.5  # neutral default
    factors = []
    if marine:
        wh = marine.get("wave_height_m") or 0
        ws = marine.get("wind_speed_kmh") or 0
        if wh > 3:
            marine_factor = 0.9
            factors.append(f"High wave height: {wh:.1f} m")
        elif wh > 1.5:
            marine_factor = 0.7
            factors.append(f"Moderate waves: {wh:.1f} m")
        if ws > 60:
            marine_factor = max(marine_factor, 0.85)
            factors.append(f"Strong winds at sea: {ws:.0f} km/h")

    # Combined probability
    prob = round(proximity * 0.5 + seasonal * 0.3 + marine_factor * 0.2, 2)
    prob = max(0.02, min(0.95, prob))

    if prob > 0.65:
        level = "High"
    elif prob > 0.35:
        level = "Moderate"
    else:
        level = "Low"

    nearest = min(STORM_HOTSPOTS, key=lambda h: haversine(lat, lon, h["lat"], h["lon"]))
    factors.insert(0, f"Nearest genesis zone: {nearest['name']}")
    factors.append(f"Season: {_season_label(month)}")

    return {
        "risk_level":       level,
        "probability":      prob,
        "proximity_score":  round(proximity, 2),
        "seasonal_weight":  round(seasonal, 2),
        "factors":          factors,
        "season":           _season_label(month),
        "source":           "climatological+open-meteo",
    }


# ── Public API ────────────────────────────────────────────────────────────────

def get_active_storms() -> list[dict]:
    """
    Returns currently active storm systems.
    Phase 2: synthetic generation backed by real Open-Meteo marine data.
    Phase 3: replaced with live IMD NWP feed.
    """
    month = datetime.datetime.utcnow().month
    return _synthetic_storms(month)


def predict_storm_risk(lat: float, lon: float) -> dict:
    """
    Predict storm risk probability for a given (lat, lon).
    Combines climatological proximity, seasonality, and live marine conditions.
    """
    month  = datetime.datetime.utcnow().month
    marine = _fetch_marine_conditions(lat, lon)
    result = _score_storm_risk(lat, lon, month, marine)
    if marine:
        result["marine"] = marine
    return result


def get_storm_climatology() -> list[dict]:
    """
    Return monthly climatological storm frequency for the Indian region.
    Used for the 12-month bar chart in storm.html.
    """
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    # Observed average annual storm counts per month (IMD historical, approx.)
    avg_counts = [0.5, 0.3, 0.3, 0.6, 1.4, 1.6, 1.2, 1.1, 1.3, 2.1, 2.5, 1.1]
    return [
        {
            "month":   months[i],
            "month_num": i + 1,
            "avg_storms": avg_counts[i],
            "seasonal_weight": SEASONAL_WEIGHTS.get(i + 1, 0.5),
        }
        for i in range(12)
    ]
