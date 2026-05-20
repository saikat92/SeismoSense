# SeismoSense — India Disaster Intelligence Platform

A Python + Flask + Bootstrap 5 web app predicting Earthquake, Tsunami, Storm, Cyclone, and Flood risk for the Indian subcontinent.

## Project Status

| Phase | Module | Status |
|---|---|---|
| Phase 1 | Earthquake + Tsunami (USGS live data) | ✅ Complete |
| Phase 2 | Storm Detection (Open-Meteo marine API) | ✅ Complete |
| Phase 3 | Cyclone Prediction (IMD Best Track) | ✅ Complete |
| Phase 4 | Flood + Live deployment + INCOIS | 🔜 Planned |

## Quick Start

```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Start Flask backend (port 8000)
cd backend && python api.py

# 3. Open frontend in browser
open frontend/index.html
```

Or use the run script:
```bash
bash run.sh
```

## API Endpoints (Phase 1 + 2)

| Method | Endpoint | Description |
|---|---|---|
| GET | /health | Server health check |
| GET | /heatmap | Earthquake heatmap (USGS) |
| GET | /seismic-trend | 8-week earthquake trend |
| GET | /live-seismic | Latest earthquake event |
| GET | /stats | Training dataset stats |
| POST | /predict_earthquake | Earthquake risk for lat/lon |
| POST | /tsunami-risk | Tsunami threat assessment |
| GET | /tsunami-events | Recent potential tsunami triggers |
| GET | /storm-alerts | Active storm systems |
| GET | /storm-climatology | Monthly storm frequency (IMD) |
| POST | /storm-marine | Marine conditions (Open-Meteo) |
| POST | /predict_storm | Storm risk for lat/lon |
| GET | /cyclone-track | Active cyclone systems (stub) |
| POST | /predict_cyclone | Cyclone risk for lat/lon (stub) |
| POST | /flood-risk | Flood risk via precipitation data |

## Data Sources

| Source | Data | Phase |
|---|---|---|
| USGS FDSNWS | Earthquakes (live) | 1 |
| Open-Meteo Marine API | Wave height, wind at sea | 2 |
| Open-Meteo Forecast | Surface pressure, precipitation | 2 |
| IMD Climatology | Storm frequency (historical) | 2 |
| INCOIS | Tsunami advisories | 4 |
| IMD Best Track | Cyclone historical tracks | 3 |

## Folder Structure

```
disaster_ml/
├── backend/
│   ├── api.py                  # Flask entry point — all endpoints
│   ├── seismic_risk.py         # Earthquake risk scoring
│   ├── usgs_service.py         # USGS FDSNWS live feed
│   ├── tsunami_service.py      # Tsunami threat assessment
│   ├── storm_service.py        # Storm detection (Phase 2)
│   ├── cyclone_service.py      # Cyclone prediction (Phase 3 stub)
│   ├── flood_service.py        # Flood risk via Open-Meteo
│   ├── geo_utils.py            # Haversine distance helper
│   ├── ml/                     # Trained model pickles (Phase 3)
│   ├── data/                   # Training CSVs
│   └── requirements.txt
├── frontend/
│   ├── index.html              # Main dashboard
│   ├── earthquake.html         # Earthquake + Tsunami module
│   ├── storm.html              # Storm module (Phase 2)
│   ├── cyclone.html            # Cyclone module (Phase 3)
│   └── static/
│       ├── css/style.css
│       └── js/map.js
├── run.sh
└── README.md
```
