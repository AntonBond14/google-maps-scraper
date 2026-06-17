#!/usr/bin/env python3
"""Build modular Da Nang restaurant dashboard pages from enriched JSON.

The input JSON is treated as read-only. This script writes map/zones pages and
shared assets next to the output HTML. It preserves an existing list page.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOURIST_KEYWORDS = (
    "an thuong",
    "my khe",
    "my an",
    "vo nguyen giap",
    "nguyen van thoai",
    "pham van dong",
    "ho nghinh",
    "son tra",
    "bach dang",
    "han river",
    "dragon bridge",
    "tran phu",
    "le quang dao",
)

LINE_ZONES = [
    {
        "id": "beachfront",
        "label": "Beachfront / first line (approx.)",
        "kind": "line",
        "color": "#0f8ea8",
        "description": "Approximate first-line coastal strip along My Khe and Pham Van Dong beach, fitted to the eastern restaurant cluster.",
        "polygon": [
            [108.2438, 16.0285],
            [108.2554, 16.0288],
            [108.2586, 16.0888],
            [108.2448, 16.0894],
            [108.2415, 16.0700],
            [108.2430, 16.0500],
            [108.2438, 16.0285],
        ],
    },
    {
        "id": "second",
        "label": "Second line (approx.)",
        "kind": "line",
        "color": "#399e72",
        "description": "Approximate band between beach roads and the city core, covering An Hai/My An side streets behind the beachfront.",
        "polygon": [
            [108.2340, 16.0278],
            [108.2438, 16.0285],
            [108.2430, 16.0500],
            [108.2415, 16.0700],
            [108.2448, 16.0894],
            [108.2328, 16.0894],
            [108.2318, 16.0640],
            [108.2330, 16.0450],
            [108.2340, 16.0278],
        ],
    },
    {
        "id": "third_city",
        "label": "Third line / city (approx.)",
        "kind": "line",
        "color": "#c27a31",
        "description": "Approximate city-side restaurants around Han River, Hai Chau and the inland Da Nang cluster.",
        "polygon": [
            [108.2050, 16.0260],
            [108.2340, 16.0278],
            [108.2330, 16.0450],
            [108.2318, 16.0640],
            [108.2328, 16.0894],
            [108.2050, 16.0894],
            [108.2050, 16.0260],
        ],
    },
]

AREA_ZONES = [
    {
        "id": "an_thuong_my_an",
        "label": "An Thuong / My An tourist area (approx.)",
        "kind": "area",
        "color": "#8b5cf6",
        "description": "Approximate tourist-area polygon around An Thuong streets and My An, based on the dense restaurant cluster south of Nguyen Van Thoai.",
        "polygon": [
            [108.2348, 16.0447],
            [108.2498, 16.0450],
            [108.2500, 16.0592],
            [108.2351, 16.0590],
            [108.2348, 16.0447],
        ],
    },
    {
        "id": "my_khe",
        "label": "My Khe beach area (approx.)",
        "kind": "area",
        "color": "#0ea5a8",
        "description": "Approximate My Khe beach corridor from Vo Nguyen Giap/Pham Van Dong through the beach-facing restaurant cluster.",
        "polygon": [
            [108.2398, 16.0515],
            [108.2528, 16.0517],
            [108.2529, 16.0764],
            [108.2412, 16.0761],
            [108.2398, 16.0515],
        ],
    },
    {
        "id": "han_dragon",
        "label": "Han River / Dragon Bridge area (approx.)",
        "kind": "area",
        "color": "#2f6fbd",
        "description": "Approximate Han River and Dragon Bridge dining area covering the Bach Dang, Tran Phu and bridge-adjacent cluster.",
        "polygon": [
            [108.2140, 16.0542],
            [108.2328, 16.0542],
            [108.2329, 16.0765],
            [108.2142, 16.0765],
            [108.2140, 16.0542],
        ],
    },
    {
        "id": "son_tra_man_thai",
        "label": "Son Tra / Man Thai area (approx.)",
        "kind": "area",
        "color": "#64748b",
        "description": "Approximate northern Son Tra/Man Thai pocket, included because the current data has restaurants in this cluster.",
        "polygon": [
            [108.2398, 16.0738],
            [108.2536, 16.0738],
            [108.2538, 16.0875],
            [108.2395, 16.0875],
            [108.2398, 16.0738],
        ],
    },
]


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def point_in_polygon(lon: float, lat: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = point
        xj, yj = polygon[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def has_messenger(row: dict[str, Any]) -> bool:
    for channel in ("whatsapp", "zalo", "telegram", "messenger", "viber"):
        if row.get(f"{channel}_url"):
            return True
        if row.get(f"{channel}_status") in {"valid", "unknown"}:
            return True
    return False


def text_blob(row: dict[str, Any]) -> str:
    fields = [row.get("title"), row.get("category"), row.get("address"), row.get("website")]
    complete = row.get("complete_address") or {}
    if isinstance(complete, dict):
        fields.extend(complete.values())
    return " ".join(str(value or "") for value in fields).lower()


def classify_line(row: dict[str, Any]) -> str:
    lat = as_number(row.get("latitude"))
    lon = as_number(row.get("longitude"))
    if lat is not None and lon is not None:
        for zone in LINE_ZONES:
            if point_in_polygon(lon, lat, zone["polygon"]):
                return str(zone["id"])

    blob = text_blob(row)
    if any(keyword in blob for keyword in ("vo nguyen giap", "my khe", "pham van dong", "ho nghinh", "beach")):
        return "beachfront"
    if any(keyword in blob for keyword in ("an thuong", "nguyen van thoai", "le quang dao", "my an")):
        return "second"
    if lon is None:
        return "unknown"
    if lon >= 108.244:
        return "beachfront"
    if lon >= 108.234:
        return "second"
    return "third_city"


def area_ids_for(row: dict[str, Any]) -> list[str]:
    lat = as_number(row.get("latitude"))
    lon = as_number(row.get("longitude"))
    found: list[str] = []
    if lat is not None and lon is not None:
        for zone in AREA_ZONES:
            if point_in_polygon(lon, lat, zone["polygon"]):
                found.append(str(zone["id"]))
    blob = text_blob(row)
    if any(keyword in blob for keyword in TOURIST_KEYWORDS):
        if "an thuong" in blob or "my an" in blob or "le quang dao" in blob:
            found.append("an_thuong_my_an")
        if "my khe" in blob or "vo nguyen giap" in blob or "pham van dong" in blob:
            found.append("my_khe")
        if "bach dang" in blob or "dragon bridge" in blob or "han river" in blob or "tran phu" in blob:
            found.append("han_dragon")
        if "son tra" in blob or "man thai" in blob:
            found.append("son_tra_man_thai")
    return list(dict.fromkeys(found))


def link_value(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value:
            return str(value)
    return ""


def normalize_restaurants(restaurants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(restaurants, start=1):
        lat = as_number(row.get("latitude"))
        lon = as_number(row.get("longitude"))
        line = classify_line(row)
        areas = area_ids_for(row)
        rating = as_number(row.get("rating")) or 0.0
        reviews = int(as_number(row.get("reviews")) or 0)
        normalized.append(
            {
                "id": row.get("place_id") or row.get("cid") or f"restaurant-{index}",
                "title": row.get("title") or f"Restaurant {index}",
                "category": row.get("category") or "Restaurant",
                "address": row.get("address") or "",
                "phone": row.get("phone") or "",
                "website": row.get("website") or "",
                "rating": round(rating, 2),
                "reviews": reviews,
                "price": row.get("price_range") or "",
                "status": row.get("status") or "",
                "lat": lat,
                "lon": lon,
                "line": line,
                "areas": areas,
                "tourist": bool(areas),
                "hasPhone": bool(row.get("phone")),
                "hasWebsite": bool(row.get("website")),
                "hasMessenger": has_messenger(row),
                "maps": link_value(row, "google_maps_url", "reviews_link"),
                "whatsapp": row.get("whatsapp_url") or "",
                "zalo": row.get("zalo_url") or "",
                "telegram": row.get("telegram_url") or "",
                "messenger": row.get("messenger_url") or "",
                "viber": row.get("viber_url") or "",
                "thumbnail": row.get("thumbnail") or "",
                "searchText": text_blob(row),
            }
        )
    return normalized


def bounds(rows: list[dict[str, Any]]) -> dict[str, float]:
    points = [row for row in rows if row["lat"] is not None and row["lon"] is not None]
    if not points:
        return {"minLat": 16.02, "maxLat": 16.09, "minLon": 108.20, "maxLon": 108.26}
    lats = [float(row["lat"]) for row in points]
    lons = [float(row["lon"]) for row in points]
    pad_lat = max((max(lats) - min(lats)) * 0.08, 0.006)
    pad_lon = max((max(lons) - min(lons)) * 0.08, 0.006)
    return {
        "minLat": min(lats) - pad_lat,
        "maxLat": max(lats) + pad_lat,
        "minLon": min(lons) - pad_lon,
        "maxLon": max(lons) + pad_lon,
    }


def zone_feature(zone: dict[str, Any], count: int) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "id": zone["id"],
            "label": zone["label"],
            "kind": zone["kind"],
            "color": zone["color"],
            "approximate": True,
            "count": count,
            "description": zone["description"],
        },
        "geometry": {"type": "Polygon", "coordinates": [zone["polygon"]]},
    }


def build_payload(data: dict[str, Any], source_name: str) -> dict[str, Any]:
    restaurants = normalize_restaurants(data.get("restaurants") or [])
    line_counts = Counter(row["line"] for row in restaurants)
    area_counts = Counter(area for row in restaurants for area in row["areas"])
    zones = [zone_feature(zone, int(line_counts[zone["id"]])) for zone in LINE_ZONES]
    zones.extend(zone_feature(zone, int(area_counts[zone["id"]])) for zone in AREA_ZONES if area_counts[zone["id"]])
    with_coords = sum(1 for row in restaurants if row["lat"] is not None and row["lon"] is not None)
    ratings = [row["rating"] for row in restaurants if row["rating"]]
    return {
        "meta": {
            "query": data.get("query") or "restaurant in Da Nang, Vietnam",
            "source": source_name,
            "scrapedAt": data.get("scraped_at") or "",
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "total": len(restaurants),
            "withCoords": with_coords,
            "withoutCoords": len(restaurants) - with_coords,
            "avgRating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
        },
        "bounds": bounds(restaurants),
        "zones": {"type": "FeatureCollection", "features": zones},
        "lineCounts": dict(line_counts),
        "areaCounts": dict(area_counts),
        "restaurants": restaurants,
    }


CSS = r"""
:root {
  color-scheme: light;
  --bg: #f6f7f2;
  --panel: #ffffff;
  --ink: #172033;
  --muted: #586277;
  --line: #d6dbe6;
  --blue: #2563eb;
  --beach: #0f8ea8;
  --second: #399e72;
  --third: #c27a31;
  --tourist: #8b5cf6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", Arial, sans-serif;
  color: var(--ink);
  background: var(--bg);
}
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
.shell { max-width: 1500px; margin: 0 auto; padding: 22px 18px 48px; }
.topbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: end;
  border-bottom: 1px solid var(--line);
  padding-bottom: 16px;
  margin-bottom: 16px;
}
h1 { margin: 0 0 5px; font-size: 28px; line-height: 1.15; letter-spacing: 0; }
h2 { margin: 0 0 12px; font-size: 16px; }
.muted { color: var(--muted); }
.nav { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.nav a, .btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
  color: var(--ink);
  font-weight: 600;
  cursor: pointer;
}
.nav a.active, .btn.primary { background: var(--ink); border-color: var(--ink); color: #fff; }
.stats { display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }
.stat, .panel, .restaurant-card, .popup-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.stat { padding: 13px; min-height: 78px; }
.stat span { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 7px; }
.stat strong { display: block; font-size: 25px; line-height: 1; }
.filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  padding: 12px;
  margin-bottom: 16px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
}
input, select {
  height: 36px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 0 10px;
  font: inherit;
  color: var(--ink);
  background: #fff;
}
input[type="search"] { min-width: 260px; }
.check { display: inline-flex; gap: 6px; align-items: center; color: var(--muted); font-size: 13px; }
.count { margin-left: auto; color: var(--muted); font-size: 13px; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 16px; align-items: start; }
.layout aside .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.panel { padding: 14px; min-width: 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 10px; }
.restaurant-card { display: grid; gap: 8px; padding: 13px; min-height: 180px; cursor: pointer; }
.restaurant-card h3 { margin: 0; font-size: 16px; line-height: 1.25; }
.tags, .links { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { border-radius: 999px; padding: 3px 8px; font-size: 12px; background: #eef2f6; color: #344054; }
.tag.beachfront { background: rgba(15,142,168,.12); color: var(--beach); }
.tag.second { background: rgba(57,158,114,.12); color: var(--second); }
.tag.third_city { background: rgba(194,122,49,.14); color: var(--third); }
.tag.area { background: rgba(139,92,246,.13); color: var(--tourist); }
.small-link { border: 1px solid var(--line); border-radius: 7px; padding: 5px 8px; font-size: 12px; background: #fff; }
#leafletMap { width: 100%; height: min(72vh, 760px); min-height: 620px; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.side-list { display: grid; gap: 10px; max-height: 720px; overflow: auto; padding-right: 3px; }
.popup-card { padding: 12px; min-width: 250px; border: 0; }
.popup-card h3 { margin: 0 0 7px; font-size: 17px; }
.leaflet-popup-content { margin: 0; min-width: 260px; }
.zone-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.zone-card { padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.zone-card strong { display: block; font-size: 26px; margin-bottom: 4px; }
.missing-list { display: grid; gap: 8px; }
.empty { color: var(--muted); padding: 18px; text-align: center; border: 1px dashed var(--line); border-radius: 8px; background: #fff; }
.map-note { margin-top: 10px; font-size: 12px; color: var(--muted); }
.marker-pin {
  width: 28px;
  height: 28px;
  border-radius: 50% 50% 50% 0;
  border: 2px solid #fff;
  box-shadow: 0 2px 8px rgba(23, 32, 51, .32);
  transform: rotate(-45deg);
}
.marker-pin span {
  display: block;
  width: 10px;
  height: 10px;
  margin: 7px;
  background: #fff;
  border-radius: 50%;
}
.marker-cluster-small, .marker-cluster-medium, .marker-cluster-large { background-color: rgba(37, 99, 235, .18); }
.marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div { background-color: rgba(37, 99, 235, .78); color: #fff; font-weight: 700; }
@media (max-width: 1100px) {
  .layout { grid-template-columns: 1fr; }
  .stats, .zone-grid { grid-template-columns: repeat(2, 1fr); }
  .count { margin-left: 0; width: 100%; }
}
@media (max-width: 680px) {
  .shell { padding: 14px 10px 34px; }
  .topbar { grid-template-columns: 1fr; }
  .nav { justify-content: flex-start; }
  .stats, .zone-grid, .cards { grid-template-columns: 1fr; }
  input[type="search"], input, select { width: 100%; }
  #leafletMap { min-height: 520px; height: 68vh; }
}
"""


JS = r"""
const DATA = window.DANANG_DASHBOARD_DATA;
const byId = id => document.getElementById(id);
const lineLabels = {
  beachfront: 'Beachfront / first line',
  second: 'Second line',
  third_city: 'Third line / city',
  unknown: 'No coordinates'
};
const lineColors = {
  beachfront: '#0f8ea8',
  second: '#399e72',
  third_city: '#c27a31',
  unknown: '#64748b'
};
const areaLabels = Object.fromEntries((DATA.zones?.features || []).map(feature => [feature.properties.id, feature.properties.label]));
let map;
let clusterLayer;
let heatLayer;
let zoneLayer;
let markerById = new Map();
let filteredCache = [];

function esc(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

function hasCoords(row) {
  return row.lat !== null && row.lon !== null && Number.isFinite(row.lat) && Number.isFinite(row.lon);
}

function contactLinks(row) {
  const links = [];
  if (row.phone) links.push(`<a class="small-link" href="tel:${esc(row.phone)}">Phone</a>`);
  if (row.website) links.push(`<a class="small-link" href="${esc(row.website)}" target="_blank" rel="noopener">Website</a>`);
  if (row.maps) links.push(`<a class="small-link" href="${esc(row.maps)}" target="_blank" rel="noopener">Google Maps</a>`);
  if (row.whatsapp) links.push(`<a class="small-link" href="${esc(row.whatsapp)}" target="_blank" rel="noopener">WhatsApp</a>`);
  if (row.zalo) links.push(`<a class="small-link" href="${esc(row.zalo)}" target="_blank" rel="noopener">Zalo</a>`);
  if (row.telegram) links.push(`<a class="small-link" href="${esc(row.telegram)}" target="_blank" rel="noopener">Telegram</a>`);
  if (row.messenger) links.push(`<a class="small-link" href="${esc(row.messenger)}" target="_blank" rel="noopener">Messenger</a>`);
  return links.join('');
}

function areaTags(row) {
  return (row.areas || []).map(id => `<span class="tag area">${esc(areaLabels[id] || id)}</span>`).join('');
}

function cardHtml(row) {
  return `<article class="restaurant-card" data-id="${esc(row.id)}">
    <h3>${esc(row.title)}</h3>
    <div class="tags">
      <span class="tag">${esc(row.category)}</span>
      <span class="tag ${esc(row.line)}">${esc(lineLabels[row.line] || row.line)}</span>
      ${areaTags(row)}
      ${row.price ? `<span class="tag">${esc(row.price)}</span>` : ''}
    </div>
    <div class="muted">${esc(row.address || 'No address')}</div>
    <div><strong>${(row.rating || 0).toFixed(1)}</strong> rating &middot; ${row.reviews || 0} reviews</div>
    <div class="links">${contactLinks(row)}</div>
  </article>`;
}

function popupHtml(row) {
  return `<div class="popup-card">
    <h3>${esc(row.title)}</h3>
    <div class="tags">
      <span class="tag">${esc(row.category)}</span>
      <span class="tag ${esc(row.line)}">${esc(lineLabels[row.line] || row.line)}</span>
      ${areaTags(row)}
    </div>
    <p class="muted">${esc(row.address || 'No address')}</p>
    <p><strong>${(row.rating || 0).toFixed(1)}</strong> rating &middot; ${row.reviews || 0} reviews</p>
    ${row.phone ? `<p>Phone: <a href="tel:${esc(row.phone)}">${esc(row.phone)}</a></p>` : ''}
    ${row.website ? `<p>Website: <a href="${esc(row.website)}" target="_blank" rel="noopener">${esc(row.website)}</a></p>` : ''}
    <div class="links">${contactLinks(row)}</div>
  </div>`;
}

function currentFilters() {
  return {
    q: (byId('search')?.value || '').trim().toLowerCase(),
    zone: byId('zoneFilter')?.value || 'all',
    rating: Number(byId('ratingFilter')?.value || 0),
    phone: Boolean(byId('hasPhone')?.checked),
    website: Boolean(byId('hasWebsite')?.checked),
    messenger: Boolean(byId('hasMessenger')?.checked),
  };
}

function matchesFilters(row, f) {
  if (f.q && !row.searchText.includes(f.q)) return false;
  if (f.zone !== 'all') {
    const [kind, id] = f.zone.split(':');
    if (kind === 'line' && row.line !== id) return false;
    if (kind === 'area' && !(row.areas || []).includes(id)) return false;
  }
  if ((row.rating || 0) < f.rating) return false;
  if (f.phone && !row.hasPhone) return false;
  if (f.website && !row.hasWebsite) return false;
  if (f.messenger && !row.hasMessenger) return false;
  return true;
}

function filteredRows() {
  const filters = currentFilters();
  return DATA.restaurants.filter(row => matchesFilters(row, filters));
}

function visibleRows(rows) {
  if (!map) return rows;
  const bounds = map.getBounds();
  return rows.filter(row => hasCoords(row) && bounds.contains([row.lat, row.lon]));
}

function wireFilters(render) {
  ['search', 'zoneFilter', 'ratingFilter', 'hasPhone', 'hasWebsite', 'hasMessenger'].forEach(id => {
    const el = byId(id);
    if (!el) return;
    el.addEventListener(id === 'search' ? 'input' : 'change', render);
  });
}

function renderStats(rows) {
  const mount = byId('stats');
  if (!mount) return;
  const rated = rows.filter(row => row.rating);
  const avg = rated.length ? rated.reduce((sum, row) => sum + row.rating, 0) / rated.length : 0;
  const items = [
    ['Visible', rows.length],
    ['Total', DATA.meta.total],
    ['With coords', rows.filter(hasCoords).length],
    ['Avg rating', avg ? avg.toFixed(2) : 'n/a'],
    ['Area-tagged', rows.filter(row => (row.areas || []).length).length],
  ];
  mount.innerHTML = items.map(([label, value]) => `<div class="stat"><span>${label}</span><strong>${value}</strong></div>`).join('');
}

function renderListPage() {
  const rows = filteredRows().sort((a, b) => (b.rating - a.rating) || (b.reviews - a.reviews));
  renderStats(rows);
  byId('cards').innerHTML = rows.length ? rows.map(cardHtml).join('') : '<div class="empty">No restaurants match the filters.</div>';
  byId('count').textContent = `${rows.length} of ${DATA.restaurants.length}`;
}

function markerIcon(row) {
  const color = row.areas?.length ? '#8b5cf6' : (lineColors[row.line] || lineColors.unknown);
  return L.divIcon({
    className: '',
    html: `<div class="marker-pin" style="background:${color}"><span></span></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
  });
}

function fitToData() {
  const points = DATA.restaurants.filter(hasCoords).map(row => [row.lat, row.lon]);
  if (points.length) {
    map.fitBounds(points, { padding: [28, 28], maxZoom: 14 });
  } else {
    map.setView([16.067, 108.235], 13);
  }
}

function initMap(showZones) {
  if (map) return;
  map = L.map('leafletMap', { scrollWheelZoom: true, preferCanvas: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);
  clusterLayer = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 42 });
  clusterLayer.addTo(map);
  heatLayer = L.heatLayer([], { radius: 28, blur: 22, maxZoom: 17, minOpacity: 0.25 }).addTo(map);
  zoneLayer = L.geoJSON(DATA.zones, {
    style: feature => ({
      color: feature.properties.color,
      fillColor: feature.properties.color,
      weight: feature.properties.kind === 'line' ? 1.5 : 2,
      opacity: 0.72,
      fillOpacity: feature.properties.kind === 'line' ? 0.13 : 0.19,
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`<strong>${esc(p.label)}</strong><br>${esc(p.description)}<br><span class="muted">${p.count} restaurants in current data. Boundary is approximate.</span>`);
    },
  });
  if (showZones) zoneLayer.addTo(map);
  L.control.layers(
    {},
    { 'Approximate zones': zoneLayer, 'Restaurant clusters': clusterLayer, 'Heatmap density': heatLayer },
    { collapsed: false }
  ).addTo(map);
  map.on('moveend zoomend', renderMapSidePanel);
  fitToData();
}

function drawMap(rows) {
  filteredCache = rows;
  markerById = new Map();
  clusterLayer.clearLayers();
  const heatPoints = [];
  rows.filter(hasCoords).forEach(row => {
    const marker = L.marker([row.lat, row.lon], { icon: markerIcon(row), title: row.title });
    marker.bindPopup(popupHtml(row));
    marker.on('click', () => selectRestaurant(row.id, false));
    markerById.set(String(row.id), marker);
    clusterLayer.addLayer(marker);
    heatPoints.push([row.lat, row.lon, Math.max(0.35, Math.min(1, (row.reviews || 1) / 3500))]);
  });
  heatLayer.setLatLngs(heatPoints);
  renderMapSidePanel();
}

function renderMapSidePanel() {
  const rows = visibleRows(filteredCache);
  renderStats(rows);
  renderSideList(rows);
  byId('count').textContent = `${rows.length} visible on map / ${filteredCache.length} filtered`;
}

function selectRestaurant(id, center = true) {
  const row = DATA.restaurants.find(item => String(item.id) === String(id));
  const marker = markerById.get(String(id));
  if (!row || !marker) return;
  if (center && hasCoords(row)) {
    map.setView([row.lat, row.lon], Math.max(map.getZoom(), 16), { animate: false });
  }
  clusterLayer.zoomToShowLayer(marker, () => {
    marker.openPopup();
    map.panTo(marker.getLatLng(), { animate: false });
  });
}

function renderMissing(rows) {
  const missing = rows.filter(row => !hasCoords(row));
  const mount = byId('missing');
  if (!mount) return;
  mount.innerHTML = missing.length
    ? missing.map(cardHtml).join('')
    : '<div class="empty">All visible restaurants have coordinates.</div>';
}

function renderSideList(rows) {
  const mount = byId('sideList');
  if (!mount) return;
  mount.innerHTML = rows.length ? rows.slice(0, 100).map(cardHtml).join('') : '<div class="empty">No visible restaurants in the current map view.</div>';
  mount.querySelectorAll('.restaurant-card').forEach(card => {
    card.addEventListener('click', event => {
      if (event.target.closest('a')) return;
      selectRestaurant(card.dataset.id);
    });
  });
}

function renderMapPage() {
  initMap(false);
  const rows = filteredRows();
  drawMap(rows);
  renderMissing(rows);
}

function renderZoneCards(rows) {
  const mount = byId('zoneCards');
  if (!mount) return;
  mount.innerHTML = (DATA.zones.features || []).map(feature => {
    const id = feature.properties.id;
    const count = feature.properties.kind === 'line'
      ? rows.filter(row => row.line === id).length
      : rows.filter(row => (row.areas || []).includes(id)).length;
    const rated = rows.filter(row => row.rating && (feature.properties.kind === 'line' ? row.line === id : (row.areas || []).includes(id)));
    const avg = rated.length ? (rated.reduce((sum, row) => sum + row.rating, 0) / rated.length).toFixed(2) : 'n/a';
    return `<div class="zone-card">
      <strong style="color:${esc(feature.properties.color)}">${count}</strong>
      <div>${esc(feature.properties.label)}</div>
      <div class="muted">Avg rating ${avg}. Approximate polygon.</div>
    </div>`;
  }).join('');
}

function renderZonesPage() {
  initMap(true);
  const rows = filteredRows();
  renderZoneCards(rows);
  drawMap(rows);
  renderMissing(rows);
}

function init() {
  const page = document.body.dataset.page;
  if (page === 'list') {
    wireFilters(renderListPage);
    renderListPage();
  } else if (page === 'map') {
    wireFilters(renderMapPage);
    renderMapPage();
  } else if (page === 'zones') {
    wireFilters(renderZonesPage);
    renderZonesPage();
  }
}

document.addEventListener('DOMContentLoaded', init);
"""


def page_shell(page: str, title: str, body: str) -> str:
    active = {"list": "", "map": "", "zones": ""}
    active[page] = " active"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
  <link rel="stylesheet" href="assets/danang-dashboard.css">
</head>
<body data-page="{page}">
  <div class="shell">
    <header class="topbar">
      <div>
        <h1>{title}</h1>
        <div class="muted">Da Nang restaurants from Google Maps. Generated from enriched JSON.</div>
      </div>
      <nav class="nav" aria-label="Dashboard navigation">
        <a class="{active['list'].strip()}" href="dashboard.html">Full list</a>
        <a class="{active['map'].strip()}" href="map.html">Map</a>
        <a class="{active['zones'].strip()}" href="zones.html">Zones</a>
      </nav>
    </header>
{body}
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
  <script src="assets/danang-restaurants-data.js"></script>
  <script src="assets/danang-dashboard.js"></script>
</body>
</html>
"""


def zone_options() -> str:
    options = [
        '<option value="all">All zones</option>',
        '<option value="line:beachfront">Beachfront / first line</option>',
        '<option value="line:second">Second line</option>',
        '<option value="line:third_city">Third line / city</option>',
    ]
    for zone in AREA_ZONES:
        options.append(f'<option value="area:{zone["id"]}">{zone["label"]}</option>')
    return "\n    ".join(options)


def filters() -> str:
    return f"""
<section class="filters" aria-label="Filters">
  <input id="search" type="search" placeholder="Search name, category, address">
  <select id="zoneFilter" aria-label="Zone or line">
    {zone_options()}
  </select>
  <select id="ratingFilter" aria-label="Minimum rating">
    <option value="0">Any rating</option>
    <option value="4">Rating 4.0+</option>
    <option value="4.3">Rating 4.3+</option>
    <option value="4.5">Rating 4.5+</option>
    <option value="4.8">Rating 4.8+</option>
  </select>
  <label class="check"><input id="hasPhone" type="checkbox"> Has phone</label>
  <label class="check"><input id="hasWebsite" type="checkbox"> Has website</label>
  <label class="check"><input id="hasMessenger" type="checkbox"> Has messengers</label>
  <span id="count" class="count"></span>
</section>
"""


def list_body() -> str:
    return f"""
{filters()}
<section id="stats" class="stats"></section>
<main id="cards" class="cards"></main>
"""


def map_body() -> str:
    return f"""
{filters()}
<div class="layout">
  <main>
    <section class="panel">
      <h2>Interactive Da Nang restaurant map</h2>
      <div id="leafletMap"></div>
      <div class="map-note">OpenStreetMap base map with clustered restaurant markers and heatmap density. The visible list follows the current map bounds.</div>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Without coordinates</h2>
      <div id="missing" class="missing-list"></div>
    </section>
  </main>
  <aside>
    <section id="stats" class="stats"></section>
    <section class="panel">
      <h2>Visible restaurants</h2>
      <div id="sideList" class="side-list"></div>
    </section>
  </aside>
</div>
"""


def zones_body() -> str:
    return f"""
{filters()}
<section id="zoneCards" class="zone-grid"></section>
<div class="layout">
  <main>
    <section class="panel">
      <h2>Approximate restaurant zones on real map</h2>
      <div id="leafletMap"></div>
      <div class="map-note">All polygons are approximate GeoJSON overlays. They were fitted from the current restaurant coordinate spread plus Da Nang beach, Han River and tourist-area landmarks.</div>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Without coordinates</h2>
      <div id="missing" class="missing-list"></div>
    </section>
  </main>
  <aside>
    <section id="stats" class="stats"></section>
    <section class="panel">
      <h2>Visible restaurants</h2>
      <div id="sideList" class="side-list"></div>
    </section>
  </aside>
</div>
"""


def write_dashboard(json_path: Path, output_dir: Path) -> list[Path]:
    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    payload = build_payload(data, json_path.name)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = [
        assets_dir / "danang-dashboard.css",
        assets_dir / "danang-dashboard.js",
        assets_dir / "danang-restaurants-data.js",
        output_dir / "map.html",
        output_dir / "zones.html",
    ]
    paths[0].write_text(CSS.strip() + "\n", encoding="utf-8")
    paths[1].write_text(JS.strip() + "\n", encoding="utf-8")
    paths[2].write_text(
        "window.DANANG_DASHBOARD_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    dashboard_path = output_dir / "dashboard.html"
    if not dashboard_path.exists():
        dashboard_path.write_text(page_shell("list", "Da Nang Restaurants - Full List", list_body()), encoding="utf-8")
        paths.append(dashboard_path)
    paths[3].write_text(page_shell("map", "Da Nang Restaurants - Map", map_body()), encoding="utf-8")
    paths[4].write_text(page_shell("zones", "Da Nang Restaurants - Zones", zones_body()), encoding="utf-8")
    return paths


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/build_danang_dashboard_pages.py <enriched.json> [output-dir]")
        return 2
    json_path = Path(sys.argv[1]).resolve()
    if not json_path.exists():
        print(f"JSON not found: {json_path}")
        return 1
    output_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else json_path.parent
    paths = write_dashboard(json_path, output_dir)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
