#!/usr/bin/env python3
"""Create a self-contained market view for Google Maps scraper CSV output."""

from __future__ import annotations

import csv
import html
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def as_float(value: str) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def as_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def clean_text(value: str, fallback: str = "Unknown") -> str:
    value = (value or "").strip()
    return value if value else fallback


def clean_price(value: str) -> str:
    value = clean_text(value)
    replacements = {
        "в‚¬": "EUR ",
        "РІвЂљВ¬": "EUR ",
        "Л†": "EUR ",
        "ˆ": "EUR ",
    }
    for bad, good in replacements.items():
        value = value.replace(bad, good)
    return " ".join(value.split())


def load_rows(csv_path: Path) -> list[dict[str, object]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))

    rows: list[dict[str, object]] = []
    for index, row in enumerate(raw_rows, start=1):
        rating = as_float(row.get("review_rating", ""))
        reviews = as_int(row.get("review_count", ""))
        lat = as_float(row.get("latitude", ""))
        lon = as_float(row.get("longitude", ""))
        title = clean_text(row.get("title", ""), f"Place {index}")
        category = clean_text(row.get("category", ""))
        score = 0
        if rating is not None:
            score += rating * 20
        if reviews is not None:
            score += min(35, math.log10(max(reviews, 1)) * 12)
        if row.get("website"):
            score += 4
        if row.get("phone"):
            score += 2

        rows.append(
            {
                "title": title,
                "category": category,
                "address": clean_text(row.get("address", ""), ""),
                "website": clean_text(row.get("website", ""), ""),
                "phone": clean_text(row.get("phone", ""), ""),
                "price": clean_price(row.get("price_range", "")),
                "rating": rating,
                "reviews": reviews,
                "lat": lat,
                "lon": lon,
                "link": clean_text(row.get("link", ""), "#"),
                "score": round(score, 1),
            }
        )
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    ratings = [float(row["rating"]) for row in rows if row["rating"] is not None]
    reviews = [int(row["reviews"]) for row in rows if row["reviews"] is not None]
    categories = Counter(str(row["category"]) for row in rows)
    prices = Counter(str(row["price"]) for row in rows)
    with_website = sum(1 for row in rows if row["website"])
    with_phone = sum(1 for row in rows if row["phone"])
    high_rating = [row for row in rows if row["rating"] is not None and float(row["rating"]) >= 4.7]

    return {
        "places": len(rows),
        "avg_rating": round(statistics.mean(ratings), 2) if ratings else None,
        "median_reviews": int(statistics.median(reviews)) if reviews else None,
        "max_reviews": max(reviews) if reviews else None,
        "categories": categories.most_common(),
        "prices": prices.most_common(),
        "website_rate": round(with_website / len(rows) * 100) if rows else 0,
        "phone_rate": round(with_phone / len(rows) * 100) if rows else 0,
        "high_rating_count": len(high_rating),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def build_html(csv_path: Path, rows: list[dict[str, object]], summary: dict[str, object]) -> str:
    data_json = json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False)
    source = html.escape(csv_path.name)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google Maps Market View</title>
  <style>
    :root {{
      --bg: #f4f5f2;
      --ink: #151a22;
      --muted: #667085;
      --panel: #ffffff;
      --line: #d7dce2;
      --blue: #1f6feb;
      --green: #1f8a5b;
      --red: #b42318;
      --amber: #b54708;
      --chip: #eef2f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", Tahoma, sans-serif;
      font-size: 14px;
    }}
    .shell {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 20px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
      margin-bottom: 16px;
    }}
    h1 {{
      font-size: 28px;
      line-height: 1.2;
      margin: 0 0 6px;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 15px;
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    .source, .muted {{
      color: var(--muted);
    }}
    .toolbar {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    input, select, button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      height: 36px;
      padding: 0 10px;
      font: inherit;
    }}
    button {{
      cursor: pointer;
      background: var(--ink);
      color: #fff;
      border-color: var(--ink);
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .kpi, .panel, .place {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .kpi {{
      padding: 12px;
      min-height: 84px;
    }}
    .kpi span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .kpi strong {{
      font-size: 25px;
      line-height: 1;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }}
    .stack {{
      display: grid;
      gap: 16px;
    }}
    .panel {{
      padding: 14px;
      min-width: 0;
    }}
    .bars {{
      display: grid;
      gap: 9px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(88px, 135px) 1fr 34px;
      gap: 8px;
      align-items: center;
    }}
    .bar-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bar-track {{
      height: 10px;
      background: #edf1f5;
      border-radius: 5px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: var(--blue);
    }}
    .map {{
      width: 100%;
      height: 430px;
      border: 1px solid var(--line);
      background:
        linear-gradient(#e7edf5 1px, transparent 1px),
        linear-gradient(90deg, #e7edf5 1px, transparent 1px),
        #f9fbfd;
      background-size: 42px 42px;
      border-radius: 8px;
      display: block;
    }}
    .main-grid {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .matrix {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }}
    .cell {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-height: 76px;
      background: #fbfcfd;
    }}
    .cell strong {{
      display: block;
      font-size: 22px;
      margin-bottom: 4px;
    }}
    .places {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .place {{
      padding: 12px;
      min-height: 145px;
      display: grid;
      align-content: start;
      gap: 8px;
    }}
    .place h3 {{
      margin: 0;
      font-size: 15px;
      line-height: 1.25;
    }}
    .meta {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .chip {{
      background: var(--chip);
      border-radius: 999px;
      padding: 3px 7px;
      color: #344054;
      font-size: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      border-bottom: 1px solid #e7ebef;
      padding: 8px 7px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      cursor: pointer;
      white-space: nowrap;
    }}
    td a {{
      color: var(--blue);
      text-decoration: none;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    @media (max-width: 1180px) {{
      .kpis {{ grid-template-columns: repeat(3, 1fr); }}
      .layout, .main-grid {{ grid-template-columns: 1fr; }}
      .places {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 680px) {{
      .shell {{ padding: 12px; }}
      header {{ grid-template-columns: 1fr; }}
      .toolbar {{ justify-content: stretch; }}
      input, select, button {{ width: 100%; }}
      .kpis, .places, .matrix {{ grid-template-columns: 1fr; }}
      .map {{ height: 320px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>Google Maps Market View</h1>
        <div class="source">Source: {source}</div>
      </div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search place or category">
        <select id="category"></select>
        <button id="reset" type="button">Reset</button>
      </div>
    </header>

    <section class="kpis" id="kpis"></section>

    <div class="layout">
      <aside class="stack">
        <section class="panel">
          <h2>Category Mix</h2>
          <div id="categoryBars" class="bars"></div>
        </section>
        <section class="panel">
          <h2>Price Coverage</h2>
          <div id="priceBars" class="bars"></div>
        </section>
      </aside>

      <main>
        <div class="main-grid">
          <section class="panel">
            <h2>Location Spread</h2>
            <svg id="map" class="map" role="img" aria-label="Location spread"></svg>
          </section>
          <section class="panel">
            <h2>Quality Segments</h2>
            <div id="matrix" class="matrix"></div>
          </section>
        </div>

        <section class="panel" style="margin-bottom:16px">
          <h2>Best Opportunities</h2>
          <div id="places" class="places"></div>
        </section>

        <section class="panel">
          <h2>All Places</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th data-sort="title">Title</th>
                  <th data-sort="category">Category</th>
                  <th data-sort="rating">Rating</th>
                  <th data-sort="reviews">Reviews</th>
                  <th data-sort="score">Score</th>
                  <th data-sort="price">Price</th>
                </tr>
              </thead>
              <tbody id="table"></tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  </div>

  <script id="dataset" type="application/json">{html.escape(data_json)}</script>
  <script>
    const source = JSON.parse(document.getElementById('dataset').textContent);
    const rows = source.rows;
    const summary = source.summary;
    const state = {{ search: '', category: 'All', sort: 'score', direction: -1 }};

    const byId = id => document.getElementById(id);
    const fmt = value => value === null || value === undefined || value === '' ? 'n/a' : value;
    const numberSort = key => ['rating', 'reviews', 'score'].includes(key);

    function filteredRows() {{
      const needle = state.search.toLowerCase();
      return rows.filter(row => {{
        const textMatch = !needle || `${{row.title}} ${{row.category}} ${{row.address}}`.toLowerCase().includes(needle);
        const categoryMatch = state.category === 'All' || row.category === state.category;
        return textMatch && categoryMatch;
      }}).sort((a, b) => {{
        const av = a[state.sort];
        const bv = b[state.sort];
        if (numberSort(state.sort)) {{
          return ((av ?? -1) - (bv ?? -1)) * state.direction;
        }}
        return String(av ?? '').localeCompare(String(bv ?? '')) * state.direction;
      }});
    }}

    function renderKpis(list) {{
      const ratings = list.map(row => row.rating).filter(value => value !== null);
      const reviews = list.map(row => row.reviews).filter(value => value !== null).sort((a, b) => a - b);
      const avgRating = ratings.length ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(2) : 'n/a';
      const medianReviews = reviews.length ? reviews[Math.floor(reviews.length / 2)] : 'n/a';
      const topScore = list.length ? Math.max(...list.map(row => row.score)).toFixed(1) : 'n/a';
      const websiteRate = list.length ? Math.round(list.filter(row => row.website).length / list.length * 100) + '%' : 'n/a';
      const items = [
        ['Visible places', list.length],
        ['Avg rating', avgRating],
        ['Median reviews', medianReviews],
        ['Top score', topScore],
        ['With website', websiteRate],
        ['Generated', summary.generated_at],
      ];
      byId('kpis').innerHTML = items.map(([label, value]) => `<div class="kpi"><span>${{label}}</span><strong>${{value}}</strong></div>`).join('');
    }}

    function renderBars(id, pairs, color) {{
      const max = Math.max(1, ...pairs.map(item => item[1]));
      byId(id).innerHTML = pairs.slice(0, 12).map(([label, count]) => `
        <div class="bar-row" title="${{label}}: ${{count}}">
          <div class="bar-label">${{label}}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${{count / max * 100}}%;background:${{color}}"></div></div>
          <div class="muted">${{count}}</div>
        </div>
      `).join('');
    }}

    function renderMap(list) {{
      const svg = byId('map');
      const points = list.filter(row => row.lat !== null && row.lon !== null);
      svg.innerHTML = '';
      svg.setAttribute('viewBox', '0 0 900 430');
      if (!points.length) return;
      const lats = points.map(row => row.lat);
      const lons = points.map(row => row.lon);
      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
      const minLon = Math.min(...lons), maxLon = Math.max(...lons);
      const latSpan = Math.max(0.001, maxLat - minLat);
      const lonSpan = Math.max(0.001, maxLon - minLon);
      const maxReviews = Math.max(1, ...points.map(row => row.reviews || 0));
      for (const row of points) {{
        const x = 28 + ((row.lon - minLon) / lonSpan) * 844;
        const y = 402 - ((row.lat - minLat) / latSpan) * 374;
        const radius = 5 + Math.sqrt((row.reviews || 0) / maxReviews) * 14;
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x.toFixed(2));
        circle.setAttribute('cy', y.toFixed(2));
        circle.setAttribute('r', radius.toFixed(2));
        circle.setAttribute('fill', row.rating >= 4.7 ? '#1f8a5b' : row.rating >= 4.4 ? '#1f6feb' : '#b54708');
        circle.setAttribute('fill-opacity', '0.55');
        circle.setAttribute('stroke', '#151a22');
        circle.setAttribute('stroke-width', '0.7');
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${{row.title}} | ${{row.rating}} | ${{row.reviews}} reviews`;
        circle.appendChild(title);
        svg.appendChild(circle);
      }}
    }}

    function segmentLabel(row) {{
      if ((row.rating ?? 0) >= 4.7 && (row.reviews ?? 0) >= 500) return 'Proven leaders';
      if ((row.rating ?? 0) >= 4.7) return 'Highly rated';
      if ((row.reviews ?? 0) >= 1000) return 'High visibility';
      if ((row.rating ?? 0) < 4.2) return 'Weak rating';
      if ((row.reviews ?? 0) < 100) return 'Low proof';
      return 'Stable middle';
    }}

    function renderMatrix(list) {{
      const counts = new Map();
      for (const row of list) counts.set(segmentLabel(row), (counts.get(segmentLabel(row)) || 0) + 1);
      const labels = ['Proven leaders', 'Highly rated', 'High visibility', 'Stable middle', 'Low proof', 'Weak rating'];
      byId('matrix').innerHTML = labels.map(label => `<div class="cell"><strong>${{counts.get(label) || 0}}</strong><div>${{label}}</div></div>`).join('');
    }}

    function renderPlaces(list) {{
      byId('places').innerHTML = list.slice(0, 9).map(row => `
        <article class="place">
          <h3><a href="${{row.link}}" target="_blank" rel="noopener noreferrer">${{row.title}}</a></h3>
          <div class="muted">${{row.category}}</div>
          <div class="meta">
            <span class="chip">Rating ${{fmt(row.rating)}}</span>
            <span class="chip">${{fmt(row.reviews)}} reviews</span>
            <span class="chip">Score ${{fmt(row.score)}}</span>
          </div>
          <div class="muted">${{row.address || 'No address'}}</div>
        </article>
      `).join('');
    }}

    function renderTable(list) {{
      byId('table').innerHTML = list.map(row => `
        <tr>
          <td><a href="${{row.link}}" target="_blank" rel="noopener noreferrer">${{row.title}}</a></td>
          <td>${{row.category}}</td>
          <td>${{fmt(row.rating)}}</td>
          <td>${{fmt(row.reviews)}}</td>
          <td>${{fmt(row.score)}}</td>
          <td>${{row.price}}</td>
        </tr>
      `).join('');
    }}

    function render() {{
      const list = filteredRows();
      renderKpis(list);
      renderMap(list);
      renderMatrix(list);
      renderPlaces([...list].sort((a, b) => b.score - a.score));
      renderTable(list);
    }}

    function setup() {{
      const categorySelect = byId('category');
      const categories = ['All', ...new Set(rows.map(row => row.category).sort())];
      categorySelect.innerHTML = categories.map(category => `<option value="${{category}}">${{category}}</option>`).join('');
      renderBars('categoryBars', summary.categories, 'var(--blue)');
      renderBars('priceBars', summary.prices, 'var(--green)');
      byId('search').addEventListener('input', event => {{ state.search = event.target.value; render(); }});
      categorySelect.addEventListener('change', event => {{ state.category = event.target.value; render(); }});
      byId('reset').addEventListener('click', () => {{
        state.search = '';
        state.category = 'All';
        byId('search').value = '';
        categorySelect.value = 'All';
        render();
      }});
      document.querySelectorAll('th[data-sort]').forEach(th => {{
        th.addEventListener('click', () => {{
          const key = th.dataset.sort;
          state.direction = state.sort === key ? state.direction * -1 : (numberSort(key) ? -1 : 1);
          state.sort = key;
          render();
        }});
      }});
      render();
    }}

    setup();
  </script>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/visualize_gmaps_market.py <csv-path>")
        return 2

    csv_path = Path(sys.argv[1]).resolve()
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return 1

    rows = load_rows(csv_path)
    if not rows:
        print(f"No rows found in {csv_path}")
        return 1

    output_path = csv_path.with_name(f"{csv_path.stem}-market.html")
    output_path.write_text(build_html(csv_path, rows, summarize(rows)), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
