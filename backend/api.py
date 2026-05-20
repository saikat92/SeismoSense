"""
SeismoSense — Disaster Intelligence Platform API  v4.0
Phases 1-4 complete: Earthquake · Tsunami · Storm · Cyclone · Flood
Unified alert bus, real-time polling, production-ready error handling.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import random, datetime, logging, os

from seismic_risk    import calculate_seismic_activity, calculate_risk_probability
from usgs_service    import fetch_recent_earthquakes
from tsunami_service import assess_tsunami_risk, get_recent_tsunami_events
from storm_service   import get_active_storms, predict_storm_risk
from cyclone_service import get_active_cyclones, predict_cyclone_risk

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code

def _parse_latlon(body):
    lat = body.get("lat"); lon = body.get("lon")
    if lat is None or lon is None:
        return None, None, "Missing required fields: lat, lon"
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None, "lat and lon must be numeric"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, "lat must be in [-90,90] and lon in [-180,180]"
    return lat, lon, None

# ── Health ───────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": _now(), "version": "4.0.0"})

# ── EARTHQUAKE ───────────────────────────────────────────────────────────────

@app.route("/heatmap", methods=["GET"])
def heatmap_data():
    try:
        quakes = fetch_recent_earthquakes(days=7)
        points = [{"latitude": eq["lat"], "longitude": eq["lon"],
                   "intensity": min(eq["mag"]/8.0, 1.0), "magnitude": eq["mag"],
                   "depth": eq["depth"], "place": eq.get("place", "")}
                  for eq in quakes if eq.get("mag") is not None]
        source = "usgs"
    except Exception as exc:
        logger.warning("USGS heatmap failed: %s", exc)
        points = _synthetic_heatmap(); source = "synthetic"
    return jsonify({"status": "success", "source": source,
                    "count": len(points), "data": points, "updated_at": _now()})

def _synthetic_heatmap():
    return [{"latitude": round(random.uniform(5.0,35.0),3),
             "longitude": round(random.uniform(68.0,97.0),3),
             "intensity": round(random.uniform(0.2,1.0),2),
             "magnitude": round(random.uniform(2.5,6.5),1),
             "depth": round(random.uniform(5,300),1),
             "place": "Synthetic — India region"} for _ in range(80)]

@app.route("/seismic-trend", methods=["GET"])
def seismic_trend():
    try:
        quakes = fetch_recent_earthquakes(days=56)
        weeks  = _aggregate_by_week(quakes); source = "usgs"
    except Exception as exc:
        logger.warning("Trend failed: %s", exc)
        weeks = _synthetic_trend(); source = "synthetic"
    return jsonify({"status": "success", "source": source, "data": weeks})

def _aggregate_by_week(quakes):
    from collections import defaultdict
    counts = defaultdict(int); today = datetime.date.today()
    for eq in quakes:
        ts = eq.get("time")
        if ts:
            try:
                d = datetime.datetime.utcfromtimestamp(ts/1000).date()
                counts[d - datetime.timedelta(days=d.weekday())] += 1
            except Exception: pass
    result = []
    for i in range(7,-1,-1):
        m = today - datetime.timedelta(weeks=i, days=today.weekday())
        result.append({"week": m.strftime("%b %d"), "count": counts.get(m, 0)})
    return result

def _synthetic_trend():
    today = datetime.date.today()
    return [{"week": (today - datetime.timedelta(weeks=7-i)).strftime("%b %d"),
             "count": random.randint(3,18)} for i in range(8)]

@app.route("/predict_earthquake", methods=["POST"])
def predict_earthquake():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    try:
        score, nearby = calculate_seismic_activity(lat, lon)
        risk_level, probability = calculate_risk_probability(score); source = "usgs"
    except Exception as exc:
        logger.warning("Seismic calc failed: %s", exc)
        probability = round(random.uniform(0.1,0.85),2)
        risk_level = "High" if probability>0.7 else ("Moderate" if probability>0.4 else "Low")
        nearby, score, source = [], 0, "fallback"
    return jsonify({"status":"success","source":source,"lat":lat,"lon":lon,
                    "risk_level":risk_level,"probability":round(probability,2),
                    "activity_score":round(score,2),"nearby_earthquakes":len(nearby),
                    "updated_at":_now()})

@app.route("/live-seismic", methods=["GET"])
def live_seismic():
    try:
        quakes = fetch_recent_earthquakes(days=1, min_mag=2.5)
        if not quakes: raise ValueError("empty")
        q = quakes[0]
        event = {"latitude":q["lat"],"longitude":q["lon"],"magnitude":q["mag"],
                 "depth":q["depth"],"place":q.get("place",""),
                 "time": datetime.datetime.utcfromtimestamp(q["time"]/1000).isoformat()+"Z"
                         if q.get("time") else _now(),
                 "source":"usgs"}
    except Exception as exc:
        logger.warning("Live seismic failed: %s", exc)
        event = {"latitude":round(random.uniform(8,34),3),
                 "longitude":round(random.uniform(68,97),3),
                 "magnitude":round(random.uniform(2.5,6.5),1),
                 "depth":round(random.uniform(5,200),1),
                 "place":"Synthetic — India region","time":_now(),"source":"synthetic"}
    return jsonify({"status":"success","event":event})

@app.route("/stats", methods=["GET"])
def dataset_stats():
    try:
        import pandas as pd
        csv_path = os.path.join(os.path.dirname(__file__),"data","earthquake_features_sample.csv")
        df = pd.read_csv(csv_path)
        stats = {"total_records":int(len(df)),
                 "magnitude":{"min":round(float(df["magnitude"].min()),2),
                              "max":round(float(df["magnitude"].max()),2),
                              "mean":round(float(df["magnitude"].mean()),2)},
                 "depth":{"min":round(float(df["depth"].min()),2),
                          "max":round(float(df["depth"].max()),2),
                          "mean":round(float(df["depth"].mean()),2)},
                 "risk_distribution":df["risk"].value_counts().to_dict()}
        return jsonify({"status":"success","stats":stats})
    except Exception as exc:
        logger.error("Stats error: %s", exc)
        return _err("Could not compute statistics", 500)

# ── TSUNAMI ──────────────────────────────────────────────────────────────────

@app.route("/tsunami-risk", methods=["POST"])
def tsunami_risk():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    try:
        result = assess_tsunami_risk(lat, lon); source = "usgs-derived"
    except Exception as exc:
        logger.warning("Tsunami risk failed: %s", exc)
        result = {"threat_level":"None","probability":0.02,"ocean_zone":"Unknown",
                  "coast_distance_km":0,"trigger_events":[],"advisory":"Service unavailable."}
        source = "fallback"
    return jsonify({"status":"success","source":source,"lat":lat,"lon":lon,
                    **result,"updated_at":_now()})

@app.route("/tsunami-events", methods=["GET"])
def tsunami_events():
    try:
        events = get_recent_tsunami_events(days=30); source = "usgs-derived"
    except Exception as exc:
        logger.warning("Tsunami events failed: %s", exc)
        events = []; source = "fallback"
    return jsonify({"status":"success","source":source,"count":len(events),
                    "data":events,"updated_at":_now()})

# ── STORM ────────────────────────────────────────────────────────────────────

@app.route("/storm-alerts", methods=["GET"])
def storm_alerts():
    try:
        storms = get_active_storms(); source = storms[0]["source"] if storms else "synthetic"
    except Exception as exc:
        logger.warning("Storm alerts failed: %s", exc)
        storms, source = [], "fallback"
    return jsonify({"status":"success","source":source,"count":len(storms),
                    "data":storms,"updated_at":_now()})

@app.route("/predict_storm", methods=["POST"])
def predict_storm():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    try:
        result = predict_storm_risk(lat, lon)
    except Exception as exc:
        logger.warning("Storm predict failed: %s", exc)
        result = {"risk_level":"Low","probability":0.1,"source":"fallback"}
    return jsonify({"status":"success","lat":lat,"lon":lon,**result,"updated_at":_now()})

@app.route("/storm-climatology", methods=["GET"])
def storm_climatology():
    from storm_service import get_storm_climatology
    return jsonify({"status":"success","source":"imd-historical",
                    "data":get_storm_climatology(),"updated_at":_now()})

@app.route("/storm-marine", methods=["POST"])
def storm_marine():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    from storm_service import _fetch_marine_conditions, _fetch_surface_pressure
    marine   = _fetch_marine_conditions(lat, lon) or {}
    pressure = _fetch_surface_pressure(lat, lon)
    if pressure: marine["surface_pressure_hpa"] = round(pressure, 1)
    return jsonify({"status":"success","lat":lat,"lon":lon,**marine,"updated_at":_now()})

# ── CYCLONE ──────────────────────────────────────────────────────────────────

@app.route("/cyclone-track", methods=["GET"])
def cyclone_track():
    try:
        cyclones = get_active_cyclones(); source = "synthetic+open-meteo"
    except Exception as exc:
        logger.warning("Cyclone track failed: %s", exc)
        cyclones, source = [], "fallback"
    return jsonify({"status":"success","source":source,"count":len(cyclones),
                    "data":cyclones,"updated_at":_now()})

@app.route("/predict_cyclone", methods=["POST"])
def predict_cyclone():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    try:
        result = predict_cyclone_risk(lat, lon)
    except Exception as exc:
        logger.warning("Cyclone predict failed: %s", exc)
        result = {"risk_level":"Low","probability":0.05,"source":"fallback"}
    return jsonify({"status":"success","lat":lat,"lon":lon,**result,"updated_at":_now()})

@app.route("/cyclone-climatology", methods=["GET"])
def cyclone_climatology():
    from cyclone_service import get_cyclone_climatology
    return jsonify({"status":"success","source":"imd-best-track-1990-2023",
                    "data":get_cyclone_climatology(),"updated_at":_now()})

@app.route("/cyclone-history", methods=["GET"])
def cyclone_history():
    from cyclone_service import get_historical_cyclones
    return jsonify({"status":"success","source":"imd-best-track",
                    "data":get_historical_cyclones(),"updated_at":_now()})

@app.route("/cyclone-atmospheric", methods=["POST"])
def cyclone_atmospheric():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    from cyclone_service import _fetch_atmospheric
    atmo = _fetch_atmospheric(lat, lon)
    if not atmo:
        return jsonify({"status":"success","source":"fallback","lat":lat,"lon":lon,
                        "message":"Atmospheric data unavailable","updated_at":_now()})
    return jsonify({"status":"success","lat":lat,"lon":lon,**atmo,"updated_at":_now()})

# ── FLOOD (Phase 4) ──────────────────────────────────────────────────────────

@app.route("/flood-risk", methods=["POST"])
def flood_risk():
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    try:
        from flood_service import predict_flood_risk
        result = predict_flood_risk(lat, lon)
    except Exception as exc:
        logger.warning("Flood predict error: %s", exc)
        result = {"risk_level":"Low","probability":0.05,"source":"fallback","factors":[],
                  "metrics":{},"forecast":{"dates":[],"daily_mm":[]}}
    return jsonify({"status":"success","lat":lat,"lon":lon,**result,"updated_at":_now()})

@app.route("/flood-forecast", methods=["POST"])
def flood_forecast():
    """POST { lat, lon } → 7-day daily precipitation forecast array."""
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)
    try:
        from flood_service import predict_flood_risk
        result = predict_flood_risk(lat, lon)
        return jsonify({"status":"success","lat":lat,"lon":lon,
                        "forecast": result.get("forecast",{}),
                        "basin":    result.get("basin",""),
                        "updated_at":_now()})
    except Exception as exc:
        return jsonify({"status":"success","lat":lat,"lon":lon,
                        "forecast":{"dates":[],"daily_mm":[]},"updated_at":_now()})

# ── UNIFIED ALERT BUS (Phase 4) ──────────────────────────────────────────────

@app.route("/alerts", methods=["GET"])
def unified_alerts():
    """
    Single endpoint that aggregates all active hazard alerts.
    Clients poll this every 15s instead of 4 separate calls.
    Returns sorted list of alerts by severity (Critical → Low).
    """
    alerts = []

    SEVERITY = {"Critical":5,"Warning":4,"High":4,"Advisory":3,"Moderate":2,"Watch":2,"Low":1,"None":0}

    # Tsunami
    try:
        ts_events = get_recent_tsunami_events(days=7)
        for ev in ts_events:
            if ev.get("threat","None") != "None":
                alerts.append({
                    "id":       f"TS-{ev['lat']:.1f}-{ev['lon']:.1f}",
                    "hazard":   "tsunami",
                    "icon":     "🌊",
                    "level":    ev["threat"],
                    "severity": SEVERITY.get(ev["threat"], 0),
                    "title":    f"Tsunami {ev['threat']}",
                    "body":     f"M{ev['mag']} event — {ev.get('place','')}, {ev['coast_dist_km']} km from coast",
                    "eta":      f"{ev['eta_minutes']} min" if ev.get("eta_minutes") else None,
                    "color":    "#D4537E",
                })
    except Exception as exc:
        logger.warning("Alerts: tsunami fetch failed: %s", exc)

    # Active cyclones
    try:
        for cy in get_active_cyclones():
            alerts.append({
                "id":       cy["id"],
                "hazard":   "cyclone",
                "icon":     "🌀",
                "level":    cy["category_code"],
                "severity": cy.get("saffir", 1) + 2,
                "title":    cy["name"],
                "body":     f"{cy['category']} — {cy['basin']}, {cy['wind_kmh']} km/h winds",
                "eta":      f"Landfall T+{cy['landfall']['eta_hours']}h" if cy.get("landfall") else None,
                "color":    cy["color"],
            })
    except Exception as exc:
        logger.warning("Alerts: cyclone fetch failed: %s", exc)

    # Active storms
    try:
        for st in get_active_storms():
            if st.get("severity", 0) >= 2:          # Depression and above only
                alerts.append({
                    "id":       st["id"],
                    "hazard":   "storm",
                    "icon":     "⛈️",
                    "level":    st["category"],
                    "severity": st.get("severity", 1),
                    "title":    st["name"],
                    "body":     f"{st['category']} — {st['basin']}, {st['wind_kmh']} km/h",
                    "eta":      None,
                    "color":    st["color"],
                })
    except Exception as exc:
        logger.warning("Alerts: storm fetch failed: %s", exc)

    # Sort: highest severity first, then alphabetical
    alerts.sort(key=lambda a: -a["severity"])

    return jsonify({
        "status":     "success",
        "count":      len(alerts),
        "data":       alerts,
        "updated_at": _now(),
    })

# ── SUMMARY (Phase 4) ────────────────────────────────────────────────────────

@app.route("/summary", methods=["POST"])
def all_hazard_summary():
    """
    POST { lat, lon }
    Returns all 5 hazard predictions in a single call.
    Used by the dashboard scanner to replace 5 parallel fetches.
    """
    body = request.get_json(silent=True) or {}
    lat, lon, err = _parse_latlon(body)
    if err: return _err(err)

    results = {}

    # Earthquake
    try:
        score, nearby = calculate_seismic_activity(lat, lon)
        rl, prob = calculate_risk_probability(score)
        results["earthquake"] = {"risk_level":rl,"probability":round(prob,2),
                                  "activity_score":round(score,2),
                                  "nearby":len(nearby),"source":"usgs"}
    except Exception:
        results["earthquake"] = {"risk_level":"Low","probability":0.1,"source":"fallback"}

    # Tsunami
    try:
        ts = assess_tsunami_risk(lat, lon)
        results["tsunami"] = {"threat_level":ts["threat_level"],
                               "probability":ts["probability"],
                               "advisory":ts["advisory"],
                               "coast_distance_km":ts["coast_distance_km"],
                               "source":"usgs-derived"}
    except Exception:
        results["tsunami"] = {"threat_level":"None","probability":0.02,"source":"fallback"}

    # Storm
    try:
        results["storm"] = predict_storm_risk(lat, lon)
    except Exception:
        results["storm"] = {"risk_level":"Low","probability":0.1,"source":"fallback"}

    # Cyclone
    try:
        results["cyclone"] = predict_cyclone_risk(lat, lon)
    except Exception:
        results["cyclone"] = {"risk_level":"Low","probability":0.05,"source":"fallback"}

    # Flood
    try:
        from flood_service import predict_flood_risk
        fl = predict_flood_risk(lat, lon)
        results["flood"] = {"risk_level":fl["risk_level"],
                             "probability":fl["probability"],
                             "basin":fl.get("basin",""),
                             "factors":fl.get("factors",[])[:3],
                             "metrics":fl.get("metrics",{}),
                             "forecast":fl.get("forecast",{}),
                             "source":fl.get("source","open-meteo")}
    except Exception:
        results["flood"] = {"risk_level":"Low","probability":0.05,"source":"fallback"}

    return jsonify({"status":"success","lat":lat,"lon":lon,
                    "hazards":results,"updated_at":_now()})

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)