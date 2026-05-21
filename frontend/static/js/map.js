/* ============================================================
   SeismoSense — Map & Dashboard JS
   Handles Leaflet map, all API calls, live polling
   ============================================================ */

const API = "http://localhost:8000";
const POLL_INTERVAL_MS = 10000;  // 10 s live polling

// ── Map init ────────────────────────────────────────────────
let map, heatLayer, markerGroup;

function initMap() {
  map = L.map("main-map", {
    center: [20.5, 80.0],
    zoom: 5,
    zoomControl: true,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(map);

  markerGroup = L.layerGroup().addTo(map);
  loadHeatmap();
}

// ── Heatmap ─────────────────────────────────────────────────
function loadHeatmap() {
  fetch(`${API}/heatmap`)
    .then(r => r.json())
    .then(data => {
      setSourceBadge("eq-source", data.source);
      if (!data.data) return;

      if (heatLayer) map.removeLayer(heatLayer);

      const points = data.data.map(p => [p.latitude, p.longitude, p.intensity]);
      heatLayer = L.heatLayer(points, {
        radius: 20, blur: 15, maxZoom: 10,
        gradient: { 0.2: "#1D9E75", 0.5: "#EF9F27", 0.8: "#E24B4A", 1.0: "#7a1010" },
      }).addTo(map);

      // Place circle markers for notable quakes
      markerGroup.clearLayers();
      data.data
        .filter(p => p.magnitude >= 4.5)
        .forEach(p => {
          const color = p.magnitude >= 6 ? "#E24B4A" : p.magnitude >= 5 ? "#EF9F27" : "#1D9E75";
          const circle = L.circleMarker([p.latitude, p.longitude], {
            radius: Math.max(4, (p.magnitude - 2) * 2.5),
            color, fillColor: color, fillOpacity: 0.6,
            weight: 1, opacity: 0.8,
          });
          circle.bindPopup(`
            <strong>${p.place || "Unknown location"}</strong><br>
            Magnitude: <b>${p.magnitude}</b><br>
            Depth: ${p.depth} km
          `);
          markerGroup.addLayer(circle);
        });
    })
    .catch(() => setSourceBadge("eq-source", "error"));
}

// ── Seismic Trend Chart ──────────────────────────────────────
function loadTrend() {
  fetch(`${API}/seismic-trend`)
    .then(r => r.json())
    .then(data => {
      if (!data.data) return;
      const container  = document.getElementById("trend-bars");
      const labelsCont = document.getElementById("trend-labels");
      if (!container) return;

      const counts = data.data.map(w => w.count);
      const maxVal = Math.max(...counts, 1);

      container.innerHTML  = "";
      labelsCont.innerHTML = "";

      data.data.forEach(week => {
        const pct = Math.round((week.count / maxVal) * 100);
        const bar = document.createElement("div");
        bar.className = "trend-bar";
        bar.style.height     = pct + "%";
        bar.style.background = pct > 70 ? "#E24B4A" : pct > 40 ? "#EF9F27" : "#1D9E75";
        bar.title = `${week.week}: ${week.count} events`;
        container.appendChild(bar);

        const lbl = document.createElement("div");
        lbl.className   = "trend-label";
        lbl.textContent = week.week.split(" ")[1]; // just day number
        labelsCont.appendChild(lbl);
      });
    })
    .catch(console.warn);
}

// ── Live Seismic Feed ────────────────────────────────────────
function loadLiveFeed() {
  fetch(`${API}/live-seismic`)
    .then(r => r.json())
    .then(data => {
      if (!data.event) return;
      const ev  = data.event;
      const el  = document.getElementById("live-event");
      if (!el) return;

      const mag  = ev.magnitude;
      const cls  = mag >= 5.5 ? "mag-high" : mag >= 4.0 ? "mag-med" : "mag-low";
      const time = new Date(ev.time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

      el.innerHTML = `
        <div class="event-item">
          <div class="mag-badge ${cls}">${mag.toFixed(1)}</div>
          <div>
            <div class="event-place">${ev.place || "India region"}</div>
            <div class="event-meta">${time} UTC &nbsp;·&nbsp; ${ev.depth} km depth</div>
          </div>
          <span class="source-badge ${ev.source === "usgs" ? "sb-usgs" : "sb-synthetic"} ms-auto">${ev.source}</span>
        </div>
      `;
    })
    .catch(console.warn);
}

// ── Location Risk Scan ───────────────────────────────────────
function scanRisk() {
  const lat = parseFloat(document.getElementById("scan-lat").value);
  const lon = parseFloat(document.getElementById("scan-lon").value);

  if (isNaN(lat) || isNaN(lon)) {
    showScanResult("error", "Please enter valid coordinates.");
    return;
  }

  showScanResult("loading", "Scanning...");

  const body = JSON.stringify({ lat, lon });
  const hdrs = { "Content-Type": "application/json" };

  Promise.all([
    fetch(`${API}/predict_earthquake`, { method: "POST", headers: hdrs, body }).then(r => r.json()),
    fetch(`${API}/tsunami-risk`,       { method: "POST", headers: hdrs, body }).then(r => r.json()),
    fetch(`${API}/predict_storm`,      { method: "POST", headers: hdrs, body }).then(r => r.json()),
    fetch(`${API}/predict_cyclone`, { method: "POST", headers: hdrs, body }).then(r => r.json()),
    fetch(`${API}/flood-risk`,       { method: "POST", headers: hdrs, body }).then(r => r.json()),
    fetch(`${API}/weather-aqi`,       { method: "POST", headers: hdrs, body }).then(r => r.json()),
  ])
  .then(([eq, ts, st, cy, fl, wx]) => {
    // Drop a pin
    markerGroup.clearLayers();
    L.marker([lat, lon])
      .bindPopup(`<b>Scan point</b><br>EQ: ${eq.risk_level} (${(eq.probability*100).toFixed(0)}%)`)
      .addTo(markerGroup)
      .openPopup();
    map.setView([lat, lon], 7);

    // Update meters
    setMeter("eq",      eq.probability,  eq.risk_level);
    setMeter("tsunami", ts.probability,  ts.threat_level);
    setMeter("storm",   st.probability,  st.risk_level);
    setMeter("cyclone", cy.probability,  cy.risk_level);
    if (fl) setMeter("flood",   fl.probability || 0, fl.risk_level || "Low");
    if (wx) renderWeatherAQI(wx);

    showScanResult("ok", `
      <div class="stat-grid mt-2">
        <div class="stat-item"><div class="stat-val">${riskPill(eq.risk_level)}</div><div class="stat-lbl">Earthquake</div></div>
        <div class="stat-item"><div class="stat-val">${riskPill(ts.threat_level)}</div><div class="stat-lbl">Tsunami</div></div>
        <div class="stat-item"><div class="stat-val">${riskPill(st.risk_level)}</div><div class="stat-lbl">Storm</div></div>
        <div class="stat-item"><div class="stat-val">${riskPill(cy.risk_level)}</div><div class="stat-lbl">Cyclone</div></div>
        <div class="stat-item"><div class="stat-val">${riskPill((fl||{}).risk_level||"—")}</div><div class="stat-lbl">Flood</div></div>
      </div>
    `);
  })
  .catch(err => showScanResult("error", "API unreachable. Is the server running?"));
}

function showScanResult(type, html) {
  const el = document.getElementById("scan-result");
  if (!el) return;
  el.innerHTML = type === "loading"
    ? `<div class="text-center" style="color:var(--ss-muted);font-size:0.8rem">${html}</div>`
    : html;
}

// ── Risk Meters ──────────────────────────────────────────────
function setMeter(hazard, prob, level) {
  const bar  = document.getElementById(`meter-${hazard}`);
  const pill = document.getElementById(`pill-${hazard}`);
  if (bar)  bar.style.width = Math.round(prob * 100) + "%";
  if (pill) { pill.textContent = level; pill.className = `risk-pill ${levelClass(level)}`; }
}

function levelClass(level) {
  const l = (level || "").toLowerCase();
  if (l === "high"     || l === "warning"  || l === "critical") return "pill-high";
  if (l === "moderate" || l === "advisory" || l === "watch")    return "pill-mod";
  if (l === "low"      || l === "none")                         return "pill-low";
  return "pill-none";
}

function riskPill(level) {
  return `<span class="risk-pill ${levelClass(level)}">${level || "—"}</span>`;
}

// ── Alerts ───────────────────────────────────────────────────
function loadAlerts() {
  Promise.all([
    fetch(`${API}/cyclone-track`).then(r => r.json()),
    fetch(`${API}/storm-alerts`).then(r => r.json()),
    fetch(`${API}/tsunami-events`).then(r => r.json()),
  ])
  .then(([cy, st, ts]) => {
    const el = document.getElementById("alert-feed");
    if (!el) return;

    let html = "";

    (cy.data || []).slice(0, 2).forEach(c => {
      html += alertItem("🌀", "ai-cy", c.name, `${c.category} — ${c.basin}, ${c.wind_kmh} km/h`);
    });

    (ts.data || []).filter(t => t.threat !== "None").slice(0, 2).forEach(t => {
      html += alertItem("🌊", "ai-ts", "Tsunami signal", `M${t.mag} at ${t.coast_dist_km} km from coast — ${t.threat}`);
    });

    (st.data || []).slice(0, 2).forEach(s => {
      html += alertItem("⛈️", "ai-st", s.name, `${s.category}, ${s.wind_kmh} km/h winds`);
    });

    if (!html) html = `<div style="color:var(--ss-muted);font-size:0.8rem;padding:6px 0">No active alerts</div>`;
    el.innerHTML = html;
  })
  .catch(console.warn);
}

function alertItem(icon, cls, title, body) {
  return `
    <div class="alert-item">
      <div class="alert-icon ${cls}">${icon}</div>
      <div class="alert-text"><strong>${title}</strong> — ${body}</div>
    </div>
  `;
}

// ── Helpers ──────────────────────────────────────────────────
function setSourceBadge(id, source) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = source;
  el.className   = `source-badge sb-${source}`;
}

function startClock() {
  const el = document.getElementById("ss-clock");
  if (!el) return;
  setInterval(() => {
    el.textContent = new Date().toUTCString().slice(0, 25) + " UTC";
  }, 1000);
}

// ── Bootstrap ────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  initMap();
  loadTrend();
  loadLiveFeed();
  loadAlerts();
  startClock();

  // Live polling
  setInterval(() => {
    loadLiveFeed();
    loadAlerts();
  }, POLL_INTERVAL_MS);

  // Scan button
  const btn = document.getElementById("scan-btn");
  if (btn) btn.addEventListener("click", scanRisk);

  // Enter key in coord inputs
  ["scan-lat", "scan-lon"].forEach(id => {
    const inp = document.getElementById(id);
    if (inp) inp.addEventListener("keyup", e => { if (e.key === "Enter") scanRisk(); });
  });
});
// ============================================================
// WEATHER + AQI + CITIZEN TIPS  (Phase 5)
// ============================================================

function windDir(deg) {
  if (deg == null) return "—";
  const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                "S","SSW","SW","WSW","W","WNW","NW","NNW"];
  return dirs[Math.round(deg / 22.5) % 16];
}

function uvLabel(uv) {
  if (uv == null)  return {t:"—",    c:"var(--ss-muted)"};
  if (uv >= 11)    return {t:"Extreme",   c:"#9B59B6"};
  if (uv >= 8)     return {t:"Very High", c:"#E24B4A"};
  if (uv >= 6)     return {t:"High",      c:"#EF9F27"};
  if (uv >= 3)     return {t:"Moderate",  c:"#1D9E75"};
  return           {t:"Low",       c:"#378ADD"};
}

function aqiColor(band) {
  return (band && band.color) ? band.color : "var(--ss-muted)";
}

function shortDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { weekday:"short", month:"short", day:"numeric" });
}

function renderWeatherAQI(wx) {
  const card = document.getElementById("weather-card");
  if (!card) return;
  card.style.display = "";

  const badge = document.getElementById("weather-source-badge");
  if (badge) { badge.textContent = wx.source || "open-meteo"; badge.className = "source-badge sb-usgs"; }

  const cur = wx.current || {};

  // ── Current conditions ──────────────────────────────────
  const uv  = uvLabel(cur.uv_index);
  document.getElementById("weather-current").innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <div style="font-size:2rem;line-height:1">${cur.emoji || "🌡️"}</div>
      <div>
        <div style="font-size:1.4rem;font-weight:700;color:#e8f0ff">
          ${cur.temp_c != null ? cur.temp_c.toFixed(1)+"°C" : "—"}
          <span style="font-size:0.75rem;color:var(--ss-muted);font-weight:400">
            feels ${cur.feels_like_c != null ? cur.feels_like_c.toFixed(0)+"°C" : "—"}
          </span>
        </div>
        <div style="font-size:0.78rem;color:var(--ss-text)">${cur.description || "—"}</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:0.72rem;color:var(--ss-muted)">
      <div>💧 Humidity: <strong style="color:var(--ss-text)">${cur.humidity_pct != null ? cur.humidity_pct+"%" : "—"}</strong></div>
      <div>💨 Wind: <strong style="color:var(--ss-text)">${cur.wind_kmh != null ? cur.wind_kmh.toFixed(0)+" km/h "+windDir(cur.wind_dir_deg) : "—"}</strong></div>
      <div>🌡️ Pressure: <strong style="color:var(--ss-text)">${cur.pressure_hpa != null ? cur.pressure_hpa.toFixed(0)+" hPa" : "—"}</strong></div>
      <div>👁️ Visibility: <strong style="color:var(--ss-text)">${cur.visibility_km != null ? cur.visibility_km+" km" : "—"}</strong></div>
      <div>☀️ UV Index: <strong style="color:${uv.c}">${cur.uv_index != null ? cur.uv_index.toFixed(1)+" ("+uv.t+")" : "—"}</strong></div>
      <div>🌧️ Precip: <strong style="color:var(--ss-text)">${cur.precip_mm != null ? cur.precip_mm.toFixed(1)+" mm" : "—"}</strong></div>
    </div>
  `;

  // ── AQI panel ──────────────────────────────────────────
  const aqiEl = document.getElementById("aqi-panel");
  if (wx.aqi && wx.aqi.value != null) {
    const aqi  = wx.aqi;
    const band = aqi.band || {};
    const pct  = Math.min(Math.round((aqi.value / 120) * 100), 100);
    aqiEl.innerHTML = `
      <div style="font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--ss-muted);margin-bottom:4px">Air Quality Index (EU)</div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <div style="font-size:1.1rem;font-weight:700;color:${aqiColor(band)}">${aqi.value.toFixed(0)}</div>
        <div style="font-size:0.8rem;font-weight:600;color:${aqiColor(band)}">${band.label || "—"}</div>
      </div>
      <div style="height:5px;background:var(--ss-surface2);border-radius:3px;overflow:hidden;margin-bottom:5px">
        <div style="width:${pct}%;height:100%;background:${aqiColor(band)};border-radius:3px;transition:width 0.6s ease"></div>
      </div>
      <div style="font-size:0.68rem;color:var(--ss-muted);margin-bottom:5px">${band.desc || ""}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;font-size:0.68rem;color:var(--ss-muted)">
        ${aqi.pm25 != null ? `<span>PM2.5: <b style="color:var(--ss-text)">${aqi.pm25.toFixed(0)}</b></span>` : ""}
        ${aqi.pm10 != null ? `<span>PM10: <b style="color:var(--ss-text)">${aqi.pm10.toFixed(0)}</b></span>` : ""}
        ${aqi.o3 != null   ? `<span>O₃: <b style="color:var(--ss-text)">${aqi.o3.toFixed(0)}</b></span>` : ""}
        ${aqi.no2 != null  ? `<span>NO₂: <b style="color:var(--ss-text)">${aqi.no2.toFixed(0)}</b></span>` : ""}
      </div>
    `;
  } else {
    aqiEl.innerHTML = `<div style="font-size:0.75rem;color:var(--ss-muted)">AQI data unavailable</div>`;
  }

  // ── 5-day forecast strip ────────────────────────────────
  const strip = document.getElementById("forecast-strip");
  if (wx.forecast && wx.forecast.length) {
    strip.innerHTML = wx.forecast.map(d => `
      <div style="flex:0 0 auto;min-width:72px;background:var(--ss-surface2);
                  border:1px solid var(--ss-border);border-radius:7px;
                  padding:7px 6px;text-align:center">
        <div style="font-size:0.62rem;color:var(--ss-muted);margin-bottom:3px">${shortDate(d.date)}</div>
        <div style="font-size:1.1rem">${d.emoji}</div>
        <div style="font-size:0.68rem;color:var(--ss-muted);margin:2px 0">${d.description||"—"}</div>
        <div style="font-size:0.75rem;font-weight:600;color:#e8f0ff">
          ${d.temp_max_c != null ? d.temp_max_c.toFixed(0)+"°" : "—"}
          <span style="color:var(--ss-muted);font-weight:400">
            / ${d.temp_min_c != null ? d.temp_min_c.toFixed(0)+"°" : "—"}
          </span>
        </div>
        ${d.precip_mm != null && d.precip_mm > 0
          ? `<div style="font-size:0.62rem;color:#378ADD;margin-top:2px">💧${d.precip_mm.toFixed(0)}mm</div>`
          : ""}
      </div>
    `).join("");
  } else {
    strip.innerHTML = `<div style="font-size:0.75rem;color:var(--ss-muted)">No forecast data</div>`;
  }

  // ── Citizen tips ────────────────────────────────────────
  const tipsEl = document.getElementById("citizen-tips");
  const tips   = wx.tips || [];
  tipsEl.innerHTML = tips.map(t => `
    <div style="font-size:0.77rem;color:var(--ss-text);padding:5px 0;
                border-bottom:1px solid var(--ss-border);line-height:1.5">${t}</div>
  `).join("") || `<div style="font-size:0.75rem;color:var(--ss-muted)">No tips available</div>`;
}
