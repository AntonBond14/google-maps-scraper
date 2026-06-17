#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard for a Google Maps scraper CSV."""

from __future__ import annotations

import csv
import html
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_float(value: str) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    try:
        return int(float((value or "").strip()))
    except ValueError:
        return None


def compact_category(value: str) -> str:
    value = (value or "").strip()
    return value or "Unknown"


def normalize_price_range(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "Unknown"
    if value == "$$":
        return "$$"
    value = value.replace("в‚¬", "EUR ").replace("€", "EUR ").replace("ˆ", "EUR ")
    value = re.sub(r"\s+", " ", value).strip()
    if value.startswith("EUR") and not value.startswith("EUR "):
        value = value.replace("EUR", "EUR ", 1)
    return value


def parse_popular_times(raw: str) -> dict[str, dict[str, int]]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    parsed: dict[str, dict[str, int]] = {}
    for day, values in data.items():
        if not isinstance(values, dict):
            continue
        parsed[day] = {}
        for hour, score in values.items():
            try:
                parsed[day][str(hour)] = int(score)
            except (TypeError, ValueError):
                continue
    return parsed


def svg_bar_chart(items: list[tuple[str, float]], title: str, width: int = 720, bar_color: str = "#2563eb") -> str:
    chart_height = 28 * len(items) + 40
    max_value = max((value for _, value in items), default=1)
    inner_width = width - 220
    y = 24
    parts = [
        f'<section class="panel"><h2>{html.escape(title)}</h2>',
        f'<svg viewBox="0 0 {width} {chart_height}" class="chart" role="img" aria-label="{html.escape(title)}">',
    ]
    for label, value in items:
        bar_width = 0 if max_value == 0 else (value / max_value) * inner_width
        safe_label = html.escape(label)
        parts.append(f'<text x="0" y="{y}" class="axis-label">{safe_label}</text>')
        parts.append(f'<rect x="185" y="{y - 14}" width="{bar_width:.2f}" height="16" rx="5" fill="{bar_color}"></rect>')
        parts.append(f'<text x="{195 + bar_width:.2f}" y="{y}" class="value-label">{value:g}</text>')
        y += 28
    parts.append("</svg></section>")
    return "".join(parts)


def svg_rating_distribution(counts: list[tuple[str, int]]) -> str:
    return svg_bar_chart(counts, "Rating Distribution", bar_color="#16a34a")


def svg_scatter(points: list[tuple[float, float, str]], width: int = 720, height: int = 360) -> str:
    if not points:
        return '<section class="panel"><h2>Reviews vs Rating</h2><p>No numeric data.</p></section>'
    max_reviews = max(point[0] for point in points)
    min_rating = min(point[1] for point in points)
    max_rating = max(point[1] for point in points)
    rating_span = max(max_rating - min_rating, 0.1)
    left = 56
    bottom = height - 42
    top = 18
    right = width - 20
    parts = [
        '<section class="panel"><h2>Reviews vs Rating</h2>',
        '<p class="subtle">Bubble positions show review count against Google rating.</p>',
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Reviews versus rating scatter plot">',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" class="axis-line"></line>',
        f'<line x1="{left}" y1="{bottom}" x2="{left}" y2="{top}" class="axis-line"></line>',
    ]
    for tick in range(5):
        x = left + (right - left) * tick / 4
        value = max_reviews * tick / 4
        parts.append(f'<line x1="{x:.1f}" y1="{bottom}" x2="{x:.1f}" y2="{bottom + 6}" class="axis-line faint"></line>')
        parts.append(f'<text x="{x:.1f}" y="{bottom + 20}" text-anchor="middle" class="axis-label">{int(value)}</text>')
    for tick in range(6):
        y = bottom - (bottom - top) * tick / 5
        value = min_rating + rating_span * tick / 5
        parts.append(f'<line x1="{left - 6}" y1="{y:.1f}" x2="{left}" y2="{y:.1f}" class="axis-line faint"></line>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis-label">{value:.1f}</text>')
    for reviews, rating, title in points:
        x = left if max_reviews == 0 else left + (reviews / max_reviews) * (right - left)
        y = bottom - ((rating - min_rating) / rating_span) * (bottom - top)
        radius = 4 + min(10, math.sqrt(max(reviews, 0)) / 5)
        safe_title = html.escape(f"{title}: {reviews} reviews, rating {rating:.1f}")
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="#f97316" fill-opacity="0.45" stroke="#c2410c" stroke-width="1">'
            f"<title>{safe_title}</title></circle>"
        )
    parts.append(
        f'<text x="{(left + right) / 2:.1f}" y="{height - 8}" text-anchor="middle" class="axis-label">Review count</text>'
        f'<text x="18" y="{(top + bottom) / 2:.1f}" transform="rotate(-90 18 {(top + bottom) / 2:.1f})" text-anchor="middle" class="axis-label">Rating</text>'
        "</svg></section>"
    )
    return "".join(parts)


def svg_map(points: list[dict[str, object]], width: int = 720, height: int = 420) -> str:
    if not points:
        return '<section class="panel"><h2>Map Footprint</h2><p>No coordinates.</p></section>'
    lats = [point["lat"] for point in points]
    lons = [point["lon"] for point in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_span = max(max_lat - min_lat, 0.001)
    lon_span = max(max_lon - min_lon, 0.001)
    parts = [
        '<section class="panel"><h2>Map Footprint</h2>',
        '<p class="subtle">Simple latitude/longitude projection of the scraped places.</p>',
        f'<svg viewBox="0 0 {width} {height}" class="chart map" role="img" aria-label="Map footprint">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="#eff6ff"></rect>',
    ]
    for point in points:
        x = 24 + ((point["lon"] - min_lon) / lon_span) * (width - 48)
        y = height - 24 - ((point["lat"] - min_lat) / lat_span) * (height - 48)
        radius = 4 + min(12, math.sqrt(max(point["reviews"], 0)) / 6)
        safe_title = html.escape(f'{point["title"]} | {point["category"]} | {point["rating"]:.1f}')
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="#2563eb" fill-opacity="0.35" stroke="#1d4ed8" stroke-width="1">'
            f"<title>{safe_title}</title></circle>"
        )
    parts.append("</svg></section>")
    return "".join(parts)


def html_table(rows: list[dict[str, object]]) -> str:
    parts = [
        '<section class="panel"><h2>Top Places by Review Count</h2>',
        '<div class="table-wrap"><table><thead><tr><th>Title</th><th>Category</th><th>Rating</th><th>Reviews</th><th>Price</th></tr></thead><tbody>',
    ]
    for row in rows:
        parts.append(
            "<tr>"
            f'<td><a href="{html.escape(str(row["link"]))}" target="_blank" rel="noopener noreferrer">{html.escape(str(row["title"]))}</a></td>'
            f'<td>{html.escape(str(row["category"]))}</td>'
            f'<td>{row["rating"]:.1f}</td>'
            f'<td>{int(row["reviews"])}</td>'
            f'<td>{html.escape(str(row["price"]))}</td>'
            "</tr>"
        )
    parts.append("</tbody></table></div></section>")
    return "".join(parts)


def render_dashboard(csv_path: Path) -> str:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise SystemExit("CSV has no data rows")

    categories = Counter()
    price_ranges = Counter()
    rating_buckets = Counter()
    review_counts: list[int] = []
    ratings: list[float] = []
    scatter_points: list[tuple[float, float, str]] = []
    map_points: list[dict[str, object]] = []
    hourly_popularity = defaultdict(int)
    top_places: list[dict[str, object]] = []

    for row in rows:
        title = (row.get("title") or "").strip() or "Untitled"
        category = compact_category(row.get("category") or "")
        price = normalize_price_range(row.get("price_range") or "")
        review_count = parse_int(row.get("review_count") or "")
        rating = parse_float(row.get("review_rating") or "")
        lat = parse_float(row.get("latitude") or "")
        lon = parse_float(row.get("longitude") or "")

        categories[category] += 1
        price_ranges[price] += 1

        if rating is not None:
            ratings.append(rating)
            if rating < 4.0:
                rating_buckets["< 4.0"] += 1
            elif rating < 4.2:
                rating_buckets["4.0 - 4.2"] += 1
            elif rating < 4.4:
                rating_buckets["4.2 - 4.4"] += 1
            elif rating < 4.6:
                rating_buckets["4.4 - 4.6"] += 1
            elif rating < 4.8:
                rating_buckets["4.6 - 4.8"] += 1
            else:
                rating_buckets["4.8+"] += 1

        if review_count is not None:
            review_counts.append(review_count)

        if review_count is not None and rating is not None:
            scatter_points.append((review_count, rating, title))
            top_places.append(
                {
                    "title": title,
                    "category": category,
                    "rating": rating,
                    "reviews": review_count,
                    "price": price,
                    "link": row.get("link") or "#",
                }
            )

        if lat is not None and lon is not None and rating is not None:
            map_points.append(
                {
                    "title": title,
                    "category": category,
                    "lat": lat,
                    "lon": lon,
                    "rating": rating,
                    "reviews": review_count or 0,
                }
            )

        popular_times = parse_popular_times(row.get("popular_times") or "")
        for values in popular_times.values():
            for hour, score in values.items():
                try:
                    hourly_popularity[int(hour)] += score
                except ValueError:
                    continue

    top_places.sort(key=lambda item: (-int(item["reviews"]), -float(item["rating"])))
    hourly_items = [(f"{hour:02d}:00", hourly_popularity[hour]) for hour in sorted(hourly_popularity)]

    cards = [
        ("Places", str(len(rows))),
        ("Categories", str(len(categories))),
        ("Avg rating", f"{statistics.mean(ratings):.2f}" if ratings else "n/a"),
        ("Median reviews", f"{statistics.median(review_counts):.0f}" if review_counts else "n/a"),
        ("Top category", categories.most_common(1)[0][0] if categories else "n/a"),
        ("Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]

    cards_html = "".join(
        f'<div class="card"><div class="card-label">{html.escape(label)}</div><div class="card-value">{html.escape(value)}</div></div>'
        for label, value in cards
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google Maps CSV Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f3;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #586277;
      --line: #d6dbe6;
      --accent: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(37,99,235,0.08), transparent 22rem),
        linear-gradient(180deg, #fcfcfa 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1300px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    h1, h2 {{ margin: 0 0 10px; }}
    p {{ margin: 0; }}
    .hero {{
      margin-bottom: 24px;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: rgba(255,255,255,0.82);
      backdrop-filter: blur(6px);
    }}
    .subtle {{
      color: var(--muted);
      line-height: 1.5;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 14px;
      margin: 22px 0 28px;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 8px 24px rgba(23,32,51,0.05);
    }}
    .card {{
      padding: 16px 18px;
    }}
    .card-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 10px;
    }}
    .card-value {{
      font-size: 28px;
      font-weight: 700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .panel {{
      padding: 18px;
      overflow: hidden;
    }}
    .panel.full {{
      grid-column: 1 / -1;
    }}
    .chart {{
      width: 100%;
      height: auto;
      display: block;
      margin-top: 10px;
    }}
    .axis-label {{
      fill: #5b6476;
      font-size: 12px;
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    .value-label {{
      fill: #172033;
      font-size: 12px;
      font-weight: 600;
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    .axis-line {{
      stroke: #94a3b8;
      stroke-width: 1;
    }}
    .axis-line.faint {{
      stroke: #cbd5e1;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin-top: 10px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid #e5e7eb;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    @media (max-width: 900px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Google Maps Scrape Dashboard</h1>
      <p class="subtle">Source: {html.escape(csv_path.name)}. This view summarizes category mix, ratings, review volume, price bands, time-of-day activity, and geographic spread for the current scrape output.</p>
      <div class="cards">{cards_html}</div>
    </section>
    <div class="grid">
      <div class="panel">{svg_bar_chart(categories.most_common(10), "Top Categories")}</div>
      <div class="panel">{svg_rating_distribution(list(rating_buckets.items()))}</div>
      <div class="panel">{svg_bar_chart(price_ranges.most_common(10), "Price Ranges", bar_color="#7c3aed")}</div>
      <div class="panel">{svg_bar_chart(hourly_items, "Aggregated Popular Hours", bar_color="#ea580c")}</div>
      <div class="panel full">{svg_scatter(scatter_points)}</div>
      <div class="panel full">{svg_map(map_points)}</div>
      <div class="panel full">{html_table(top_places[:15])}</div>
    </div>
  </div>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/visualize_gmaps_csv.py <csv-path>")
        return 2

    csv_path = Path(sys.argv[1]).resolve()
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return 1

    output_path = csv_path.with_name(f"{csv_path.stem}-dashboard.html")
    output_path.write_text(render_dashboard(csv_path), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
