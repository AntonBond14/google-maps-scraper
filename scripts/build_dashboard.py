#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard from normalized restaurant JSON.

Usage:
    python build_dashboard.py <normalized.json> [output.html]
"""
from __future__ import annotations

import html
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def esc(text) -> str:
    """HTML-escape None-safe."""
    return html.escape(str(text or ""))


def render_stars(rating: float) -> str:
    """Return HTML with filled/empty star characters."""
    if not rating:
        return '<span class="stars-muted">—</span>'
    full = int(rating)
    half = 1 if rating - full >= 0.3 else 0
    empty = 5 - full - half
    stars = "★" * full + ("★" if half else "") + "☆" * empty
    return f'<span class="stars" title="{rating:.1f}">{stars}</span>'


def action_buttons(r: dict) -> str:
    """Render action button links for a restaurant."""
    btns = []

    # Google Maps
    gmap = r.get("google_maps_url")
    if gmap:
        btns.append(
            f'<a class="btn btn-maps" href="{esc(gmap)}" target="_blank" rel="noopener">🗺️ Maps</a>'
        )

    # Phone
    phone = r.get("phone")
    if phone:
        tel = f"tel:{phone}"
        btns.append(f'<a class="btn btn-phone" href="{tel}">📞 Call</a>')

    # Website
    site = r.get("website")
    if site:
        btns.append(
            f'<a class="btn btn-web" href="{esc(site)}" target="_blank" rel="noopener">🌐 Website</a>'
        )

    # WhatsApp
    wa = r.get("whatsapp_url")
    if wa:
        btns.append(
            f'<a class="btn btn-wa" href="{esc(wa)}" target="_blank" rel="noopener">💬 WhatsApp</a>'
        )

    # Email
    email_url = r.get("email_url")
    if email_url:
        btns.append(
            f'<a class="btn btn-email" href="{esc(email_url)}">✉️ Email</a>'
        )

    return "\n".join(btns)


def social_links_html(r: dict) -> str:
    """Small inline social/external links."""
    links = r.get("social") or []
    if not links:
        return ""
    parts = []
    for s in links:
        url = s.get("url") or ""
        source = s.get("source") or s.get("host") or ""
        icon = "🔗"
        host = (s.get("host") or "").lower()
        if "facebook" in host:
            icon = "📘"
        elif "instagram" in host:
            icon = "📷"
        elif "tripadvisor" in host:
            icon = "🧭"
        elif "tiktok" in host:
            icon = "🎵"
        elif "youtube" in host:
            icon = "▶️"
        parts.append(
            f'<a class="social-link" href="{esc(url)}" target="_blank" rel="noopener" title="{esc(source)}">{icon} {esc(source)}</a>'
        )
    return '<div class="social-row">' + " ".join(parts) + "</div>"


def render_restaurant_card(r: dict) -> str:
    """Single restaurant card."""
    thumbnail = r.get("thumbnail") or ""
    thumb_html = ""
    if thumbnail:
        thumb_html = f'<img class="thumb" src="{esc(thumbnail)}" alt="" loading="lazy">'

    status = r.get("status") or ""
    status_class = "closed" if status and ("closed" in status.lower() or "temporarily" in status.lower()) else ""

    price = esc(r.get("price_range") or "")

    return f"""
<div class="card" data-rating="{r.get('rating', 0) or 0}" data-reviews="{r.get('reviews', 0) or 0}"
     data-has-phone='{"1" if r.get("phone") else "0"}'
     data-has-website='{"1" if r.get("website") else "0"}'>
  <div class="card-body">
    <div class="card-top">
      {thumb_html}
      <div class="card-info">
        <h3 class="card-title">{esc(r.get('title'))}</h3>
        <div class="card-meta">
          <span class="category">{esc(r.get('category'))}</span>
          {f'<span class="price">{price}</span>' if price else ''}
          {f'<span class="status {status_class}">{esc(status)}</span>' if status else ''}
        </div>
        <div class="card-rating">
          {render_stars(r.get("rating") or 0)}
          <span class="rating-val">{r.get("rating", 0):.1f}</span>
          <span class="review-count">({r.get("reviews", 0)})</span>
        </div>
      </div>
    </div>
    <div class="card-address">
      <span class="label">📍</span> {esc(r.get('address'))}
    </div>
    {f'<div class="card-phone"><span class="label">📱</span> <a href="tel:{esc(r.get("phone"))}">{esc(r.get("phone"))}</a></div>' if r.get("phone") else ''}
    {f'<div class="card-website"><span class="label">🌐</span> <a href="{esc(r.get("website"))}" target="_blank" rel="noopener">{esc(r.get("website"))}</a></div>' if r.get("website") else ''}
    {f'<div class="card-email"><span class="label">✉️</span> <a href="{esc(r.get("email_url"))}">{esc(r.get("email"))}</a></div>' if r.get("email") else ''}
    {social_links_html(r)}
    <div class="card-actions">
      {action_buttons(r)}
    </div>
  </div>
</div>"""


def build_dashboard(data: dict) -> str:
    restaurants = data.get("restaurants") or []
    total = data.get("total", len(restaurants))

    # Stats
    ratings = [r.get("rating") or 0 for r in restaurants if r.get("rating")]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0
    max_reviews = max((r.get("reviews") or 0 for r in restaurants), default=0)
    with_phone = sum(1 for r in restaurants if r.get("phone"))
    with_website = sum(1 for r in restaurants if r.get("website"))
    with_email = sum(1 for r in restaurants if r.get("email"))

    categories = Counter(r.get("category") or "" for r in restaurants)

    # Top 10 categories
    cat_items = "\n".join(
        f'<li><span class="cat-name">{esc(c)}</span> <span class="cat-count">{cnt}</span></li>'
        for c, cnt in categories.most_common(10)
    )

    # Rating distribution
    buckets = Counter()
    for r in restaurants:
        rt = r.get("rating") or 0
        if rt < 3.5:
            buckets["< 3.5"] += 1
        elif rt < 4.0:
            buckets["3.5–4.0"] += 1
        elif rt < 4.5:
            buckets["4.0–4.5"] += 1
        else:
            buckets["4.5+"] += 1
    bucket_items = "\n".join(
        f'<li><span class="cat-name">{esc(k)}</span> <span class="cat-count">{v}</span></li>'
        for k, v in sorted(buckets.items())
    )

    # Restaurants JSON for embedding
    restaurants_json = json.dumps(restaurants, ensure_ascii=False, indent=None)

    cards_html = f"""
<div class="stat-card">
  <div class="stat-label">Restaurants</div>
  <div class="stat-value">{total}</div>
</div>
<div class="stat-card">
  <div class="stat-label">Avg Rating</div>
  <div class="stat-value">{avg_rating:.1f} ★</div>
</div>
<div class="stat-card">
  <div class="stat-label">Max Reviews</div>
  <div class="stat-value">{max_reviews:,}</div>
</div>
<div class="stat-card">
  <div class="stat-label">With Phone</div>
  <div class="stat-value">{with_phone}/{total} ({round(100*with_phone/total)}%)</div>
</div>
<div class="stat-card">
  <div class="stat-label">With Website</div>
  <div class="stat-value">{with_website}/{total} ({round(100*with_website/total)}%)</div>
</div>
<div class="stat-card">
  <div class="stat-label">Categories</div>
  <div class="stat-value">{len(categories)}</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🍽️ Da Nang Restaurants — Dashboard</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f7f7f3;
  --panel: #ffffff;
  --ink: #172033;
  --muted: #586277;
  --line: #d6dbe6;
  --accent: #2563eb;
  --green: #16a34a;
  --orange: #ea580c;
  --red: #dc2626;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: "Segoe UI", -apple-system, Arial, sans-serif;
  color: var(--ink);
  background: radial-gradient(circle at top right, rgba(37,99,235,0.07), transparent 22rem),
              linear-gradient(180deg, #fcfcfa 0%, var(--bg) 100%);
  min-height: 100vh;
}}
.wrap {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px 16px 64px;
}}
/* Hero */
.hero {{
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(8px);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 24px 28px;
  margin-bottom: 20px;
}}
.hero h1 {{ font-size: 26px; margin-bottom: 4px; }}
.hero .sub {{ color: var(--muted); font-size: 14px; }}
/* Stats cards */
.stats {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}}
.stat-card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 4px 16px rgba(23,32,51,0.04);
}}
.stat-label {{
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}}
.stat-value {{
  font-size: 22px;
  font-weight: 700;
}}
/* Sidebar lists */
.sidebar {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}}
.sidebar-panel {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 4px 16px rgba(23,32,51,0.04);
}}
.sidebar-panel h2 {{
  font-size: 16px;
  margin-bottom: 12px;
  color: var(--ink);
}}
.sidebar-panel ul {{
  list-style: none;
  padding: 0;
}}
.sidebar-panel li {{
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0ec;
  font-size: 14px;
}}
.sidebar-panel li:last-child {{ border-bottom: none; }}
.cat-name {{ color: var(--muted); }}
.cat-count {{ font-weight: 600; color: var(--accent); }}
/* Filters */
.filters {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 16px rgba(23,32,51,0.04);
}}
.filters h2 {{ font-size: 16px; margin-bottom: 12px; }}
.filters-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}}
.filters-row label {{
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}}
.filters-row input[type="text"],
.filters-row select {{
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  font-size: 14px;
  color: var(--ink);
  background: #fff;
  outline: none;
  transition: border-color .15s;
}}
.filters-row input[type="text"]:focus,
.filters-row select:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
}}
.filters-row input[type="text"] {{ width: 280px; }}
.filters-row select {{ min-width: 150px; }}
.filter-check {{
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
}}
.filter-check input {{
  accent-color: var(--accent);
  width: 16px;
  height: 16px;
}}
#count-display {{
  font-size: 13px;
  color: var(--muted);
  margin-left: auto;
  white-space: nowrap;
}}
/* Cards grid */
.cards-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
  gap: 16px;
}}
.card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(23,32,51,0.04);
  transition: box-shadow .2s, transform .15s;
}}
.card:hover {{
  box-shadow: 0 8px 28px rgba(23,32,51,0.10);
  transform: translateY(-1px);
}}
.card-body {{ padding: 18px 20px 16px; }}
.card-top {{
  display: flex;
  gap: 14px;
  margin-bottom: 12px;
}}
.thumb {{
  width: 80px;
  height: 80px;
  border-radius: 12px;
  object-fit: cover;
  flex-shrink: 0;
  background: #f0f0ec;
}}
.card-info {{ flex: 1; min-width: 0; }}
.card-title {{
  font-size: 17px;
  font-weight: 700;
  line-height: 1.3;
  margin-bottom: 4px;
  word-break: break-word;
}}
.card-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}}
.category {{
  font-size: 12px;
  color: var(--accent);
  background: rgba(37,99,235,0.08);
  padding: 2px 8px;
  border-radius: 6px;
}}
.price {{
  font-size: 12px;
  color: var(--orange);
  background: rgba(234,88,12,0.08);
  padding: 2px 8px;
  border-radius: 6px;
}}
.status {{
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(22,163,74,0.08);
  color: var(--green);
}}
.status.closed {{
  background: rgba(220,38,38,0.08);
  color: var(--red);
}}
.card-rating {{
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}}
.stars {{
  color: #f59e0b;
  font-size: 14px;
  letter-spacing: 1px;
}}
.stars-muted {{
  color: var(--muted);
  font-size: 13px;
}}
.rating-val {{
  font-weight: 700;
  font-size: 15px;
}}
.review-count {{
  font-size: 13px;
  color: var(--muted);
}}
.card-address,
.card-phone,
.card-website,
.card-email {{
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 3px;
  word-break: break-word;
}}
.card-address a,
.card-phone a,
.card-website a,
.card-email a {{
  color: var(--accent);
  text-decoration: none;
}}
.card-address a:hover,
.card-phone a:hover,
.card-website a:hover,
.card-email a:hover {{
  text-decoration: underline;
}}
.label {{ margin-right: 4px; }}
.social-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0;
}}
.social-link {{
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  background: rgba(37,99,235,0.06);
  padding: 3px 10px;
  border-radius: 8px;
  transition: background .15s;
}}
.social-link:hover {{
  background: rgba(37,99,235,0.14);
  text-decoration: none;
}}
.card-actions {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f0f0ec;
}}
.btn {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: transform .12s, box-shadow .12s;
  border: none;
  cursor: pointer;
}}
.btn:hover {{ transform: scale(1.03); }}
.btn-phone {{ background: #dcfce7; color: #15803d; }}
.btn-web {{ background: #dbeafe; color: #1d4ed8; }}
.btn-maps {{ background: #fef3c7; color: #b45309; }}
.btn-wa {{ background: #d1fae5; color: #047857; }}
.btn-email {{ background: #ede9fe; color: #6d28d9; }}
/* No results */
.no-results {{
  text-align: center;
  padding: 60px 20px;
  color: var(--muted);
  font-size: 18px;
  grid-column: 1 / -1;
}}
/* Responsive */
@media (max-width: 600px) {{
  .cards-grid {{ grid-template-columns: 1fr; }}
  .sidebar {{ grid-template-columns: 1fr; }}
  .filters-row input[type="text"] {{ width: 100%; }}
}}
@media (max-width: 900px) {{
  .cards-grid {{ grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }}
}}
</style>
</head>
<body>
<div class="wrap">

  <!-- Hero -->
  <div class="hero">
    <h1>🍽️ Restaurants in Da Nang, Vietnam</h1>
    <p class="sub">
      Scraped from Google Maps &middot; {total} places &middot;
      Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    </p>
  </div>

  <!-- Stats -->
  <div class="stats">
    {cards_html}
  </div>

  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-panel">
      <h2>🏷️ Top Categories</h2>
      <ul>{cat_items}</ul>
    </div>
    <div class="sidebar-panel">
      <h2>⭐ Rating Distribution</h2>
      <ul>{bucket_items}</ul>
    </div>
  </div>

  <!-- Filters -->
  <div class="filters">
    <h2>🔍 Search &amp; Filter</h2>
    <div class="filters-row">
      <label>Search</label>
      <input type="text" id="search" placeholder="Restaurant name…" autocomplete="off">
      <label>Rating ≥</label>
      <select id="rating-filter">
        <option value="0">Any</option>
        <option value="3">3 ★</option>
        <option value="3.5">3.5 ★</option>
        <option value="4" selected>4 ★</option>
        <option value="4.5">4.5 ★</option>
        <option value="4.8">4.8 ★</option>
      </select>
      <label>Sort</label>
      <select id="sort">
        <option value="rating-desc">Rating ↓</option>
        <option value="rating-asc">Rating ↑</option>
        <option value="reviews-desc">Reviews ↓</option>
        <option value="reviews-asc">Reviews ↑</option>
        <option value="name-asc">Name A→Z</option>
        <option value="name-desc">Name Z→A</option>
      </select>
      <label class="filter-check"><input type="checkbox" id="has-phone" checked> Phone only</label>
      <label class="filter-check"><input type="checkbox" id="has-website"> Website only</label>
      <span id="count-display"></span>
    </div>
  </div>

  <!-- Cards -->
  <div class="cards-grid" id="grid"></div>

</div>

<script>
// Embedded data
const DATA = {restaurants_json};

const grid = document.getElementById("grid");
const searchInput = document.getElementById("search");
const ratingFilter = document.getElementById("rating-filter");
const sortSelect = document.getElementById("sort");
const hasPhone = document.getElementById("has-phone");
const hasWebsite = document.getElementById("has-website");
const countDisplay = document.getElementById("count-display");

function escapeHtml(s) {{
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}}

function starsHtml(rating) {{
  if (!rating) return '<span class="stars-muted">—</span>';
  let out = '<span class="stars" title="' + rating.toFixed(1) + '">';
  for (let i = 1; i <= 5; i++) {{
    out += i <= Math.round(rating) ? "★" : "☆";
  }}
  return out + '</span>';
}}

function renderCard(r) {{
  const phone = r.phone || "";
  const website = r.website || "";
  const email = r.email || "";
  const emailUrl = r.email_url || "";
  const status = r.status || "";
  const statusCls = status && (/closed|temporarily/i.test(status)) ? "status closed" : "status";
  const thumb = r.thumbnail ? '<img class="thumb" src="' + escapeHtml(r.thumbnail) + '" alt="" loading="lazy">' : '';

  let social = "";
  if (r.social && r.social.length) {{
    social = '<div class="social-row">';
    r.social.forEach(s => {{
      let icon = "🔗";
      const h = (s.host || "").toLowerCase();
      if (h.includes("facebook")) icon = "📘";
      else if (h.includes("instagram")) icon = "📷";
      else if (h.includes("tripadvisor")) icon = "🧭";
      else if (h.includes("tiktok")) icon = "🎵";
      else if (h.includes("youtube")) icon = "▶️";
      social += '<a class="social-link" href="' + escapeHtml(s.url) + '" target="_blank" rel="noopener" title="' + escapeHtml(s.source) + '">' + icon + " " + escapeHtml(s.source) + '</a>';
    }});
    social += "</div>";
  }}

  let btns = "";
  if (r.google_maps_url) btns += '<a class="btn btn-maps" href="' + escapeHtml(r.google_maps_url) + '" target="_blank" rel="noopener">🗺️ Maps</a>';
  if (phone) btns += '<a class="btn btn-phone" href="tel:' + escapeHtml(phone) + '">📞 Call</a>';
  if (website) btns += '<a class="btn btn-web" href="' + escapeHtml(website) + '" target="_blank" rel="noopener">🌐 Website</a>';
  if (r.whatsapp_url) btns += '<a class="btn btn-wa" href="' + escapeHtml(r.whatsapp_url) + '" target="_blank" rel="noopener">💬 WhatsApp</a>';
  if (emailUrl) btns += '<a class="btn btn-email" href="' + escapeHtml(emailUrl) + '">✉️ Email</a>';

  return `<div class="card">
  <div class="card-body">
    <div class="card-top">
      ${{thumb}}
      <div class="card-info">
        <h3 class="card-title">${{escapeHtml(r.title)}}</h3>
        <div class="card-meta">
          <span class="category">${{escapeHtml(r.category)}}</span>
          ${{r.price_range ? '<span class="price">' + escapeHtml(r.price_range) + '</span>' : ''}}
          ${{status ? '<span class="' + statusCls + '">' + escapeHtml(status) + '</span>' : ''}}
        </div>
        <div class="card-rating">
          ${{starsHtml(r.rating)}}
          <span class="rating-val">${{(r.rating || 0).toFixed(1)}}</span>
          <span class="review-count">(${{r.reviews || 0}})</span>
        </div>
      </div>
    </div>
    <div class="card-address"><span class="label">📍</span> ${{escapeHtml(r.address)}}</div>
    ${{phone ? '<div class="card-phone"><span class="label">📱</span> <a href="tel:' + escapeHtml(phone) + '">' + escapeHtml(phone) + '</a></div>' : ''}}
    ${{website ? '<div class="card-website"><span class="label">🌐</span> <a href="' + escapeHtml(website) + '" target="_blank" rel="noopener">' + escapeHtml(website) + '</a></div>' : ''}}
    ${{email ? '<div class="card-email"><span class="label">✉️</span> <a href="' + escapeHtml(emailUrl) + '">' + escapeHtml(email) + '</a></div>' : ''}}
    ${{social}}
    <div class="card-actions">${{btns}}</div>
  </div>
</div>`;
}}

function applyFilters() {{
  const q = (searchInput.value || "").trim().toLowerCase();
  const minRating = parseFloat(ratingFilter.value) || 0;
  const phoneOnly = hasPhone.checked;
  const websiteOnly = hasWebsite.checked;
  const sortVal = sortSelect.value;

  let list = DATA.slice();

  // Filter
  list = list.filter(r => {{
    if (q && !(r.title || "").toLowerCase().includes(q)) return false;
    if (r.rating < minRating) return false;
    if (phoneOnly && !r.phone) return false;
    if (websiteOnly && !r.website) return false;
    return true;
  }});

  // Sort
  switch (sortVal) {{
    case "rating-desc": list.sort((a,b) => (b.rating||0) - (a.rating||0)); break;
    case "rating-asc":  list.sort((a,b) => (a.rating||0) - (b.rating||0)); break;
    case "reviews-desc": list.sort((a,b) => (b.reviews||0) - (a.reviews||0)); break;
    case "reviews-asc":  list.sort((a,b) => (a.reviews||0) - (b.reviews||0)); break;
    case "name-asc":  list.sort((a,b) => (a.title||"").localeCompare(b.title||"")); break;
    case "name-desc": list.sort((a,b) => (b.title||"").localeCompare(a.title||"")); break;
  }}

  // Render
  if (list.length === 0) {{
    grid.innerHTML = '<div class="no-results">No restaurants match your filters.</div>';
  }} else {{
    grid.innerHTML = list.map(renderCard).join("");
  }}

  countDisplay.textContent = list.length + " of " + DATA.length;
}}

// Debounce search
let searchTimer;
searchInput.addEventListener("input", () => {{
  clearTimeout(searchTimer);
  searchTimer = setTimeout(applyFilters, 200);
}});

ratingFilter.addEventListener("change", applyFilters);
sortSelect.addEventListener("change", applyFilters);
hasPhone.addEventListener("change", applyFilters);
hasWebsite.addEventListener("change", applyFilters);

// Initial render
applyFilters();
</script>
</body>
</html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    json_path = Path(sys.argv[1]).resolve()
    if not json_path.exists():
        print(f"File not found: {json_path}")
        return 1

    out_path = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) >= 3
        else json_path.with_name("dashboard.html")
    )

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    html_content = build_dashboard(data)
    out_path.write_text(html_content, encoding="utf-8")
    size = out_path.stat().st_size
    print(f"wrote {out_path} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
