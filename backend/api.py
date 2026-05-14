"""
SeismoSense — Disaster Intelligence Platform API
Flask REST backend with earthquake + tsunami (Phase 1).
Storm and Cyclone endpoints are stubs, expanded in Phase 2 & 3.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import random
import datetime
import logging
import os

from seismic_risk   import calculate_seismic_activity, calculate_risk_probability
from usgs_service   import fetch_recent_earthquakes
from tsunami_service import assess_tsunami_risk, get_recent_tsunami_events
from storm_service  import get_active_storms, predict_storm_risk
from cyclone_service import get_active_cyclones, predict_cyclone_risk

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code

def _parse_latlon(body):
    """Parse and validate lat/lon from request JSON body."""
    lat = body.get("lat")
    lon = body.get("lon")
    if lat is None or lon is None:
        return None, None, "Missing required fields: lat, lon"
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None, "lat and lon must be numeric"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, "lat must be in [-90,90] and lon in [-180,180]"
    return lat, lon, None


# ===========================================================================
# HEALTH
# ===========================================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": _now(), "version": "1.0.0-phase1"})


# ===========================================================================
# EARTHQUAKE ENDPOINTS
# ===========================================================================

@app.route("/heatmap", methods=["GET"])
def heatmap_data():
    """Recent USGS earthquake locations as heatmap intensity points."""
    try:
        quakes = fetch_recent_earthquakes(days=7)
        points = [
            {
                "latitude":  eq["lat"],
                "longitude": eq["lon"],
                "intensity": min(eq["mag"] / 8.0, 1.0),
                "magnitude": eq["mag"],
                "depth":     eq["depth"],
                "place":     eq.get("place", ""),
            }
            for eq in quakes if eq.get("mag") is not None
        ]
        source = "usgs"
    except Exception as exc:
        logger.warning("USGS heatmap fetch failed: %s — synthetic fallback", exc)
        points = _synthetic_heatmap()
        source = "synthetic"

    return jsonify({"status": "success", "source": source,
                    "count": len(points), "data": points, "updated_at": _now()})


def _synthetic_heatmap():
    return [
        {
            "latitude":  round(random.uniform(5.0, 35.0), 3),
            "longitude": round(random.uniform(68.0, 97.0), 3),
            "intensity": round(random.uniform(0.2, 1.0), 2),
            "magnitude": round(random.uniform(2.5, 6.5), 1),
            "depth":     round(random.uniform(5, 300), 1),
            "place":     "Synthetic — India region",
        }
        for _ in range(80)
    ]


@app.route("/seismic-trend", methods=["GET"])
def seismic_trend():
    """8-week weekly earthquake counts from USGS."""
    try:
        quakes = fetch_recent_earthquakes(days=56)
        weeks  = _aggregate_by_week(quakes)
        source = "usgs"
    except Exception as exc:
        logger.warning("USGS trend fetch failed: %s — synthetic", exc)
        weeks  = _synthetic_trend()
        source = "synthetic"

    return jsonify({"status": "success", "source": source, "data": weeks})


def _aggregate_by_week(quakes):
    from collections import defaultdict
    counts = defaultdict(int)
    today  = datetime.date.today()

    for eq in quakes:
        ts = eq.get("time")
        if ts:
            try:
                d  = datetime.datetime.utcfromtimestamp(ts / 1000).date()
                monday = d - datetime.timedelta(days=d.weekday())
                counts[monday] += 1
            except Exception:
                pass

    result = []
    for i in range(7, -1, -1):
        monday = today - datetime.timedelta(weeks=i, days=today.weekday())
        result.append({"week": monday.strftime("%b %d"), "count": counts.get(monday, 0)})
    return result


def _synthetic_trend():
    today = datetime.date.today()
    return [
        {"week": (today - datetime.timedelta(weeks=7-i)).strftime("%b %d"),
         "count": random.randint(3, 18)}
        for i in range(8)
    ]


@app.route("/predict_earthquake", methods=["POST"])
def predict_earthquake():
    """
    POST { lat, lon }
    Returns risk level, probability, nearby earthquake count.
    """
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err:
        return _err(err)

    try:
        score, nearby = calculate_seismic_activity(lat, lon)
        risk_level, probability = calculate_risk_probability(score)
        source = "usgs"
    except Exception as exc:
        logger.warning("Seismic calc failed: %s — fallback", exc)
        probability = round(random.uniform(0.1, 0.85), 2)
        risk_level  = "High" if probability > 0.7 else ("Moderate" if probability > 0.4 else "Low")
        nearby, score, source = [], 0, "fallback"

    return jsonify({
        "status":              "success",
        "source":              source,
        "lat":                 lat,
        "lon":                 lon,
        "risk_level":          risk_level,
        "probability":         round(probability, 2),
        "activity_score":      round(score, 2),
        "nearby_earthquakes":  len(nearby),
        "updated_at":          _now(),
    })


@app.route("/live-seismic", methods=["GET"])
def live_seismic():
    """Most recent earthquake from USGS (or synthetic fallback)."""
    try:
        quakes = fetch_recent_earthquakes(days=1, min_mag=2.5)
        if not quakes:
            raise ValueError("No events returned")
        latest = quakes[0]
        event = {
            "latitude":  latest["lat"],
            "longitude": latest["lon"],
            "magnitude": latest["mag"],
            "depth":     latest["depth"],
            "place":     latest.get("place", ""),
            "time":      datetime.datetime.utcfromtimestamp(
                             latest["time"] / 1000).isoformat() + "Z"
                         if latest.get("time") else _now(),
            "source":    "usgs",
        }
    except Exception as exc:
        logger.warning("Live seismic failed: %s — synthetic", exc)
        event = {
            "latitude":  round(random.uniform(8, 34), 3),
            "longitude": round(random.uniform(68, 97), 3),
            "magnitude": round(random.uniform(2.5, 6.5), 1),
            "depth":     round(random.uniform(5, 200), 1),
            "place":     "Synthetic — India region",
            "time":      _now(),
            "source":    "synthetic",
        }

    return jsonify({"status": "success", "event": event})


@app.route("/stats", methods=["GET"])
def dataset_stats():
    """Descriptive stats from training CSV."""
    try:
        import pandas as pd
        csv_path = os.path.join(os.path.dirname(__file__), "data", "earthquake_features.csv")
        df = pd.read_csv(csv_path)
        stats = {
            "total_records": int(len(df)),
            "magnitude": {
                "min":  round(float(df["magnitude"].min()), 2),
                "max":  round(float(df["magnitude"].max()), 2),
                "mean": round(float(df["magnitude"].mean()), 2),
            },
            "depth": {
                "min":  round(float(df["depth"].min()), 2),
                "max":  round(float(df["depth"].max()), 2),
                "mean": round(float(df["depth"].mean()), 2),
            },
            "risk_distribution": df["risk"].value_counts().to_dict(),
        }
        return jsonify({"status": "success", "stats": stats})
    except Exception as exc:
        logger.error("Stats error: %s", exc)
        return _err("Could not compute statistics", 500)


# ===========================================================================
# TSUNAMI ENDPOINTS
# ===========================================================================

@app.route("/tsunami-risk", methods=["POST"])
def tsunami_risk():
    """
    POST { lat, lon }
    Returns tsunami threat level, ETA, wave height estimate.
    """
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err:
        return _err(err)

    try:
        result = assess_tsunami_risk(lat, lon)
        source = "usgs-derived"
    except Exception as exc:
        logger.warning("Tsunami risk failed: %s — fallback", exc)
        result = {
            "threat_level":      "None",
            "probability":       0.02,
            "ocean_zone":        "Unknown",
            "coast_distance_km": 0,
            "trigger_events":    [],
            "advisory":          "Service temporarily unavailable.",
        }
        source = "fallback"

    return jsonify({
        "status": "success",
        "source": source,
        "lat":    lat,
        "lon":    lon,
        **result,
        "updated_at": _now(),
    })


@app.route("/tsunami-events", methods=["GET"])
def tsunami_events():
    """Recent high-magnitude seismic events that could trigger tsunamis."""
    try:
        events = get_recent_tsunami_events(days=30)
        source = "usgs-derived"
    except Exception as exc:
        logger.warning("Tsunami events failed: %s", exc)
        events = []
        source = "fallback"

    return jsonify({
        "status":     "success",
        "source":     source,
        "count":      len(events),
        "data":       events,
        "updated_at": _now(),
    })


# ===========================================================================
# STORM ENDPOINTS (Phase 1 stub — expanded in Phase 2)
# ===========================================================================

@app.route("/storm-alerts", methods=["GET"])
def storm_alerts():
    """Active storm systems (synthetic Phase 1; IMD live in Phase 2)."""
    try:
        storms = get_active_storms()
        source = "synthetic"
    except Exception as exc:
        logger.warning("Storm alerts failed: %s", exc)
        storms, source = [], "fallback"

    return jsonify({
        "status":     "success",
        "source":     source,
        "count":      len(storms),
        "data":       storms,
        "updated_at": _now(),
    })


@app.route("/predict_storm", methods=["POST"])
def predict_storm():
    """POST { lat, lon } → storm risk probability."""
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err:
        return _err(err)

    try:
        result = predict_storm_risk(lat, lon)
    except Exception as exc:
        logger.warning("Storm predict failed: %s", exc)
        result = {"risk_level": "Low", "probability": 0.1, "source": "fallback"}

    return jsonify({"status": "success", "lat": lat, "lon": lon,
                    **result, "updated_at": _now()})


# ===========================================================================
# CYCLONE ENDPOINTS (Phase 1 stub — expanded in Phase 3)
# ===========================================================================

@app.route("/cyclone-track", methods=["GET"])
def cyclone_track():
    """Active cyclone systems (synthetic Phase 1; IMD Best Track in Phase 3)."""
    try:
        cyclones = get_active_cyclones()
        source   = "synthetic"
    except Exception as exc:
        logger.warning("Cyclone track failed: %s", exc)
        cyclones, source = [], "fallback"

    return jsonify({
        "status":     "success",
        "source":     source,
        "count":      len(cyclones),
        "data":       cyclones,
        "updated_at": _now(),
    })


@app.route("/predict_cyclone", methods=["POST"])
def predict_cyclone():
    """POST { lat, lon } → cyclone risk probability."""
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err:
        return _err(err)

    try:
        result = predict_cyclone_risk(lat, lon)
    except Exception as exc:
        logger.warning("Cyclone predict failed: %s", exc)
        result = {"risk_level": "Low", "probability": 0.05, "source": "fallback"}

    return jsonify({"status": "success", "lat": lat, "lon": lon,
                    **result, "updated_at": _now()})


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)


# ===========================================================================
# PHASE 2 — Additional storm endpoints
# ===========================================================================

@app.route("/storm-climatology", methods=["GET"])
def storm_climatology():
    """12-month climatological storm frequency for India."""
    from storm_service import get_storm_climatology
    return jsonify({
        "status":     "success",
        "source":     "imd-historical",
        "data":       get_storm_climatology(),
        "updated_at": _now(),
    })


@app.route("/storm-marine", methods=["POST"])
def storm_marine():
    """POST { lat, lon } → real-time marine conditions from Open-Meteo."""
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err:
        return _err(err)

    from storm_service import _fetch_marine_conditions, _fetch_surface_pressure
    marine   = _fetch_marine_conditions(lat, lon) or {}
    pressure = _fetch_surface_pressure(lat, lon)
    if pressure:
        marine["surface_pressure_hpa"] = round(pressure, 1)

    return jsonify({
        "status":     "success",
        "lat":        lat,
        "lon":        lon,
        **marine,
        "updated_at": _now(),
    })


@app.route("/flood-risk", methods=["POST"])
def flood_risk():
    """POST { lat, lon } → flood risk from Open-Meteo precipitation."""
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err:
        return _err(err)

    try:
        from flood_service import predict_flood_risk
        result = predict_flood_risk(lat, lon)
    except Exception as exc:
        logger.warning("Flood predict error: %s", exc)
        result = {"risk_level": "Low", "probability": 0.05, "source": "fallback", "factors": []}

    return jsonify({"status": "success", "lat": lat, "lon": lon,
                    **result, "updated_at": _now()})
