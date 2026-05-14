"""
Tsunami Risk Service — Phase 1
Derives tsunami threat from seismic data (USGS).
Real INCOIS integration added in Phase 4.

Tsunami triggers when:
  - Magnitude >= 6.5
  - Depth     <= 70 km  (shallow submarine quake)
  - Location is coastal / offshore (within COASTAL_BUFFER_KM of coastline proxy)

We approximate India's coastline via a set of reference points and check
the minimum distance from the earthquake epicentre to any of them.
"""

import logging
from geo_utils import haversine
from usgs_service import fetch_recent_earthquakes

logger = logging.getLogger(__name__)

# Tsunami generation thresholds
TSUNAMI_MIN_MAG   = 6.5
TSUNAMI_MAX_DEPTH = 70.0   # km
COASTAL_BUFFER_KM = 300.0  # consider epicentres within this range of coast

# Approximate India coastline reference points (lat, lon)
INDIA_COAST_POINTS = [
    # West coast (Arabian Sea)
    (8.5,  76.9),  (10.0, 76.2), (11.9, 75.4), (13.0, 74.8),
    (15.0, 73.9), (16.9, 73.3), (18.9, 72.8), (20.9, 70.9),
    (22.3, 68.9), (23.6, 68.3),
    # South tip
    (8.1,  77.5),
    # East coast (Bay of Bengal)
    (8.6,  78.1),  (9.9,  78.9), (11.0, 79.8), (12.6, 80.2),
    (14.0, 80.2), (15.8, 80.3), (17.7, 83.3), (19.3, 84.8),
    (20.3, 86.5), (21.5, 87.2),
    # Andaman & Nicobar
    (11.7, 92.7), (12.8, 92.9), (13.3, 93.1),
]

# Pre-computed threat zones for advisory text
THREAT_ZONES = {
    "Bay of Bengal":   {"lat_range": (5, 23),  "lon_range": (80, 100)},
    "Arabian Sea":     {"lat_range": (8, 25),  "lon_range": (55,  78)},
    "Andaman Sea":     {"lat_range": (6, 15),  "lon_range": (92,  100)},
    "Indian Ocean":    {"lat_range": (-10, 8), "lon_range": (55, 100)},
}


def _nearest_coast_km(lat, lon):
    return min(haversine(lat, lon, cp[0], cp[1]) for cp in INDIA_COAST_POINTS)


def _classify_threat(mag, depth, coast_dist_km):
    """
    Returns (threat_level, eta_minutes, wave_height_m_estimate).
    """
    if mag < TSUNAMI_MIN_MAG or depth > TSUNAMI_MAX_DEPTH:
        return "None", None, None

    if coast_dist_km > COASTAL_BUFFER_KM:
        return "Watch", None, None

    # Rough wave height estimate (empirical, for display only)
    # Larger mag + shallower depth + closer coast → bigger wave
    height_est = round(max(0.5, (mag - 6.0) * 2.5 * (1 - depth / 100) * (1 - coast_dist_km / 500)), 1)
    height_est = min(height_est, 15.0)

    # Tsunami speed ≈ sqrt(g * h_ocean); average ocean depth ~3500 m → ~210 m/s ≈ 756 km/h
    TSUNAMI_SPEED_KMH = 756
    eta_min = round(coast_dist_km / TSUNAMI_SPEED_KMH * 60)

    if mag >= 8.0:
        level = "Critical"
    elif mag >= 7.0:
        level = "Warning"
    else:
        level = "Advisory"

    return level, eta_min, height_est


def _identify_ocean_zone(lat, lon):
    for zone, bounds in THREAT_ZONES.items():
        if (bounds["lat_range"][0] <= lat <= bounds["lat_range"][1] and
                bounds["lon_range"][0] <= lon <= bounds["lon_range"][1]):
            return zone
    return "Open Ocean"


def assess_tsunami_risk(lat, lon):
    """
    Full tsunami risk assessment for a point (lat, lon).
    Returns a dict with threat level, ETA, wave estimate, and triggering events.
    """
    coast_dist = _nearest_coast_km(lat, lon)
    ocean_zone = _identify_ocean_zone(lat, lon)

    # Pull recent high-magnitude quakes
    try:
        quakes = fetch_recent_earthquakes(days=7, min_mag=5.5)
    except Exception as exc:
        logger.warning("USGS fetch for tsunami failed: %s", exc)
        quakes = []

    triggers = []
    highest_level = "None"
    order = ["None", "Watch", "Advisory", "Warning", "Critical"]

    for eq in quakes:
        eq_coast_dist = _nearest_coast_km(eq["lat"], eq["lon"])
        level, eta, wave_h = _classify_threat(eq["mag"], eq["depth"], eq_coast_dist)
        if level != "None":
            triggers.append({
                "mag":         eq["mag"],
                "depth":       eq["depth"],
                "lat":         eq["lat"],
                "lon":         eq["lon"],
                "place":       eq.get("place", ""),
                "threat":      level,
                "eta_minutes": eta,
                "wave_height_m": wave_h,
                "coast_dist_km": round(eq_coast_dist, 1),
            })
            if order.index(level) > order.index(highest_level):
                highest_level = level

    probability = {
        "None":     0.02,
        "Watch":    0.15,
        "Advisory": 0.40,
        "Warning":  0.70,
        "Critical": 0.92,
    }.get(highest_level, 0.02)

    return {
        "threat_level":      highest_level,
        "probability":       probability,
        "ocean_zone":        ocean_zone,
        "coast_distance_km": round(coast_dist, 1),
        "trigger_events":    triggers[:5],  # top 5 most relevant
        "advisory":          _build_advisory(highest_level, ocean_zone),
    }


def _build_advisory(level, zone):
    advisories = {
        "None":     f"No tsunami threat detected in {zone}.",
        "Watch":    f"Tsunami Watch — {zone}. Monitor updates. No immediate action required.",
        "Advisory": f"Tsunami Advisory — {zone}. Strong currents possible near coast. Stay alert.",
        "Warning":  f"Tsunami Warning — {zone}. Move away from coastal areas immediately.",
        "Critical": f"CRITICAL Tsunami Warning — {zone}. Evacuate coastal zones NOW.",
    }
    return advisories.get(level, "No data.")


def get_recent_tsunami_events(days=30):
    """
    Returns list of recent seismic events that could potentially trigger tsunamis.
    Used for the map overlay.
    """
    try:
        quakes = fetch_recent_earthquakes(days=days, min_mag=TSUNAMI_MIN_MAG)
    except Exception as exc:
        logger.warning("Tsunami events fetch failed: %s", exc)
        return []

    events = []
    for eq in quakes:
        coast_dist = _nearest_coast_km(eq["lat"], eq["lon"])
        level, eta, wave_h = _classify_threat(eq["mag"], eq["depth"], coast_dist)
        events.append({
            "lat":             eq["lat"],
            "lon":             eq["lon"],
            "mag":             eq["mag"],
            "depth":           eq["depth"],
            "place":           eq.get("place", ""),
            "threat":          level,
            "eta_minutes":     eta,
            "wave_height_m":   wave_h,
            "coast_dist_km":   round(coast_dist, 1),
        })

    return events
