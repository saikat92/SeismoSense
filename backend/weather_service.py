"""
Weather & AQI Service — SeismoSense Phase 5
============================================
Fetches current weather, 5-day forecast, and Air Quality Index
entirely from FREE, no-key APIs:

  • Open-Meteo Forecast API  — temperature, humidity, wind, pressure,
                               precipitation, UV index, weather code
  • Open-Meteo Air Quality API — PM2.5, PM10, O3, NO2, AQI (European)

Weather codes follow WMO standard (used by Open-Meteo).
AQI scale follows European Air Quality Index (0–500).
"""

import requests
import logging
import datetime

logger = logging.getLogger(__name__)

FORECAST_URL   = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT        = 12

# ── WMO weather code → description + emoji ──────────────────────────────────
WMO_CODES = {
    0:  ("Clear sky",            "☀️"),
    1:  ("Mainly clear",        "🌤️"),
    2:  ("Partly cloudy",       "⛅"),
    3:  ("Overcast",            "☁️"),
    45: ("Foggy",               "🌫️"),
    48: ("Rime fog",            "🌫️"),
    51: ("Light drizzle",       "🌦️"),
    53: ("Moderate drizzle",    "🌦️"),
    55: ("Dense drizzle",       "🌧️"),
    61: ("Slight rain",         "🌧️"),
    63: ("Moderate rain",       "🌧️"),
    65: ("Heavy rain",          "🌧️"),
    71: ("Slight snow",         "🌨️"),
    73: ("Moderate snow",       "❄️"),
    75: ("Heavy snow",          "❄️"),
    77: ("Snow grains",         "🌨️"),
    80: ("Slight showers",      "🌦️"),
    81: ("Moderate showers",    "🌧️"),
    82: ("Violent showers",     "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers",  "❄️"),
    95: ("Thunderstorm",        "⛈️"),
    96: ("Thunderstorm+hail",   "⛈️"),
    99: ("Thunderstorm+hail",   "⛈️"),
}

# ── European AQI bands ───────────────────────────────────────────────────────
AQI_BANDS = [
    (0,   20,  "Good",        "#1D9E75", "Air is clean. Great for outdoor activities."),
    (20,  40,  "Fair",        "#8DC63F", "Air quality is acceptable."),
    (40,  60,  "Moderate",   "#EF9F27", "Sensitive groups may be affected."),
    (60,  80,  "Poor",       "#E24B4A", "Everyone may begin to feel health effects."),
    (80,  100, "Very Poor",  "#9B59B6", "Health warnings. Avoid prolonged outdoor exposure."),
    (100, 999, "Extremely Poor","#7a1010","Serious health effects. Stay indoors."),
]

# ── Citizen tips by condition ────────────────────────────────────────────────
def _weather_tips(wmo_code: int, temp_c: float, wind_kmh: float,
                  precip_mm: float, uv: float, aqi: float | None) -> list[str]:
    tips = []

    # UV
    if uv is not None:
        if uv >= 11:
            tips.append("🕶️ Extreme UV — wear SPF 50+, hat, and avoid noon sun.")
        elif uv >= 8:
            tips.append("🧴 Very High UV — sunscreen required. Limit outdoor time 10am–4pm.")
        elif uv >= 6:
            tips.append("☀️ High UV — apply sunscreen before going out.")

    # Temperature
    if temp_c >= 42:
        tips.append("🌡️ Extreme heat alert — stay hydrated, avoid outdoors 11am–5pm.")
    elif temp_c >= 36:
        tips.append("🥵 Heat caution — drink water every 30 min, wear light clothing.")
    elif temp_c <= 8:
        tips.append("🧥 Cold weather — wear warm layers, watch for hypothermia in the elderly.")

    # Rain / precip
    if wmo_code in (82, 95, 96, 99):
        tips.append("⛈️ Thunderstorm active — stay indoors, avoid open fields and hilltops.")
    elif wmo_code in (65, 81):
        tips.append("🌧️ Heavy rain — risk of waterlogging. Avoid low-lying routes.")
    elif precip_mm > 20:
        tips.append("☔ Carry an umbrella — significant rainfall expected.")
    elif precip_mm > 5:
        tips.append("🌂 Light rain likely — keep a raincoat handy.")

    # Wind
    if wind_kmh >= 62:
        tips.append("💨 Gale-force winds — secure loose objects, avoid coastal areas.")
    elif wind_kmh >= 40:
        tips.append("🌬️ Strong winds — cyclists and pedestrians should be cautious.")

    # Fog
    if wmo_code in (45, 48):
        tips.append("🌫️ Dense fog — drive slowly with fog lights, allow extra travel time.")

    # AQI
    if aqi is not None:
        if aqi >= 80:
            tips.append("😷 Very poor air quality — wear N95 mask outdoors. Avoid exercise outside.")
        elif aqi >= 60:
            tips.append("😮‍💨 Poor AQI — limit strenuous outdoor activity. Vulnerable groups stay in.")
        elif aqi >= 40:
            tips.append("🌿 Moderate AQI — air quality acceptable but sensitive groups take care.")

    if not tips:
        tips.append("✅ Conditions look good. Stay aware of hazard alerts above.")

    return tips


def _aqi_band(aqi: float) -> dict:
    for lo, hi, label, color, desc in AQI_BANDS:
        if lo <= aqi < hi:
            return {"label": label, "color": color, "desc": desc}
    return {"label": "Unknown", "color": "#888", "desc": "No data"}


def _latest(vals: list) -> float | None:
    clean = [v for v in (vals or []) if v is not None]
    return clean[-1] if clean else None


def _take(lst, n=5):
    return (lst or [])[:n]


# ── Main public function ─────────────────────────────────────────────────────

def get_weather_and_aqi(lat: float, lon: float) -> dict:
    """
    Fetch current weather + 5-day daily forecast + AQI for (lat, lon).
    Returns a single merged dict. Falls back gracefully on partial failures.
    """
    weather = _fetch_weather(lat, lon)
    aqi     = _fetch_aqi(lat, lon)

    # Extract current values
    current_wmo  = weather.get("current_wmo")
    current_temp = weather.get("current_temp_c")
    current_wind = weather.get("current_wind_kmh", 0)
    precip_today = weather.get("precip_today_mm", 0)
    uv_now       = weather.get("uv_index_now")
    aqi_val      = aqi.get("aqi_now")

    wmo_desc, wmo_emoji = WMO_CODES.get(current_wmo, ("Unknown", "🌡️"))

    tips = _weather_tips(
        current_wmo or 0,
        current_temp or 25,
        current_wind or 0,
        precip_today or 0,
        uv_now,
        aqi_val,
    )

    aqi_info = _aqi_band(aqi_val) if aqi_val is not None else None

    return {
        "current": {
            "temp_c":       current_temp,
            "feels_like_c": weather.get("feels_like_c"),
            "humidity_pct": weather.get("humidity_pct"),
            "wind_kmh":     current_wind,
            "wind_dir_deg": weather.get("wind_dir_deg"),
            "pressure_hpa": weather.get("pressure_hpa"),
            "precip_mm":    precip_today,
            "uv_index":     uv_now,
            "weather_code": current_wmo,
            "description":  wmo_desc,
            "emoji":        wmo_emoji,
            "visibility_km":weather.get("visibility_km"),
        },
        "forecast": weather.get("forecast", []),   # 5-day daily
        "aqi": {
            "value":   aqi_val,
            "pm25":    aqi.get("pm25"),
            "pm10":    aqi.get("pm10"),
            "o3":      aqi.get("o3"),
            "no2":     aqi.get("no2"),
            "band":    aqi_info,
        } if aqi_val is not None else None,
        "tips":   tips,
        "source": "open-meteo + open-meteo-aq",
    }


def _fetch_weather(lat: float, lon: float) -> dict:
    params = {
        "latitude":  lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "weather_code", "wind_speed_10m", "wind_direction_10m",
            "precipitation", "surface_pressure", "visibility", "uv_index",
        ]),
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "wind_speed_10m_max", "uv_index_max",
            "sunrise", "sunset",
        ]),
        "wind_speed_unit": "kmh",
        "forecast_days":   6,
        "timezone":        "auto",
    }
    try:
        r = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()

        cur   = d.get("current", {})
        daily = d.get("daily", {})
        n     = min(5, len(daily.get("time", [])))

        forecast = []
        for i in range(1, n):  # skip today (index 0), show 5 future days
            code = (daily.get("weather_code") or [])[i] if i < len(daily.get("weather_code") or []) else 0
            desc, emoji = WMO_CODES.get(code, ("Unknown", "🌡️"))
            forecast.append({
                "date":        (daily.get("time") or [])[i] if i < len(daily.get("time") or []) else "",
                "weather_code": code,
                "description": desc,
                "emoji":       emoji,
                "temp_max_c":  (daily.get("temperature_2m_max") or [])[i] if i < len(daily.get("temperature_2m_max") or []) else None,
                "temp_min_c":  (daily.get("temperature_2m_min") or [])[i] if i < len(daily.get("temperature_2m_min") or []) else None,
                "precip_mm":   (daily.get("precipitation_sum") or [])[i] if i < len(daily.get("precipitation_sum") or []) else None,
                "wind_max_kmh":(daily.get("wind_speed_10m_max") or [])[i] if i < len(daily.get("wind_speed_10m_max") or []) else None,
                "uv_max":      (daily.get("uv_index_max") or [])[i] if i < len(daily.get("uv_index_max") or []) else None,
                "sunrise":     (daily.get("sunrise") or [])[i] if i < len(daily.get("sunrise") or []) else None,
                "sunset":      (daily.get("sunset") or [])[i] if i < len(daily.get("sunset") or []) else None,
            })

        vis_m = cur.get("visibility")
        return {
            "current_temp_c":  cur.get("temperature_2m"),
            "feels_like_c":    cur.get("apparent_temperature"),
            "humidity_pct":    cur.get("relative_humidity_2m"),
            "current_wind_kmh":cur.get("wind_speed_10m"),
            "wind_dir_deg":    cur.get("wind_direction_10m"),
            "pressure_hpa":    cur.get("surface_pressure"),
            "precip_today_mm": cur.get("precipitation"),
            "uv_index_now":    cur.get("uv_index"),
            "current_wmo":     cur.get("weather_code"),
            "visibility_km":   round(vis_m / 1000, 1) if vis_m else None,
            "forecast":        forecast,
        }
    except Exception as exc:
        logger.warning("Weather fetch failed for (%.2f,%.2f): %s", lat, lon, exc)
        return {}


def _fetch_aqi(lat: float, lon: float) -> dict:
    params = {
        "latitude":  lat,
        "longitude": lon,
        "current":   "european_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
    }
    try:
        r = requests.get(AIR_QUALITY_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        cur = r.json().get("current", {})
        return {
            "aqi_now": cur.get("european_aqi"),
            "pm25":    cur.get("pm2_5"),
            "pm10":    cur.get("pm10"),
            "o3":      cur.get("ozone"),
            "no2":     cur.get("nitrogen_dioxide"),
        }
    except Exception as exc:
        logger.warning("AQI fetch failed for (%.2f,%.2f): %s", lat, lon, exc)
        return {}
