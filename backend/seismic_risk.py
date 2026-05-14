"""
Seismic Risk Calculator
Computes an activity score from USGS events and maps it to a risk level.
"""

import math
import logging

from usgs_service import fetch_recent_earthquakes
from geo_utils import haversine

logger = logging.getLogger(__name__)

RADIUS_KM    = 500
MAX_SCORE_CAP = 100.0


def calculate_seismic_activity(lat, lon):
    """
    Fetch recent earthquakes and compute weighted activity score for (lat, lon).
    Score = count_nearby + sum(mag^2 for nearby events)

    Returns:
        (activity_score: float, nearby_earthquakes: list)
    """
    earthquakes = fetch_recent_earthquakes(days=30)

    nearby       = []
    total_energy = 0.0

    for eq in earthquakes:
        dist = haversine(lat, lon, eq["lat"], eq["lon"])
        if dist <= RADIUS_KM:
            nearby.append({**eq, "distance_km": round(dist, 1)})
            total_energy += eq["mag"] ** 2

    activity_score = len(nearby) + total_energy
    logger.info("Seismic activity at (%.4f, %.4f): %d nearby events, score=%.2f",
                lat, lon, len(nearby), activity_score)
    return activity_score, nearby


def calculate_risk_probability(score):
    """
    Map raw activity score → (risk_label, probability).
    Uses a sigmoid curve for smooth transitions.

    Approximate thresholds:
        score <  5  → Low      (~0.10–0.25)
        score < 20  → Moderate (~0.25–0.60)
        score >= 20 → High     (~0.60–0.90)
    """
    normalised  = min(score / MAX_SCORE_CAP, 1.0)
    probability = round(1 / (1 + math.exp(-10 * (normalised - 0.3))), 2)
    probability = max(0.05, min(0.95, probability))

    if score < 5:
        label = "Low"
    elif score < 20:
        label = "Moderate"
    else:
        label = "High"

    return label, probability
