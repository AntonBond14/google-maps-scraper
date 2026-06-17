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
