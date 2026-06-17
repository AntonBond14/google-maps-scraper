#!/usr/bin/env python3
"""Normalize raw Google Maps scraper JSONL output into a clean, flat structure.

The upstream scraper (gosom/google-maps-scraper) writes one JSON object per
line via its `jsonwriter` plugin. Each line is a full `gmaps.Entry` payload
with 30+ fields (including nested reviews, popular_times, about, etc.).

This script produces a smaller, friendlier JSON the dashboard consumes:

    {
      "query": "restaurant in Da Nang, Vietnam",
      "scraped_at": "2026-06-17T20:55:04Z",
      "total": 116,
      "missing": { ... human-readable notes about gaps ... },
      "restaurants": [
        {
          "title": "...",
          "category": "...",
          "categories": [...],
          "address": "...",
          "complete_address": {...},
          "phone": "...",
          "phone_e164": "+84...",
          "whatsapp_url": "https://wa.me/...",
          "website": "...",
          "email": "...",            // first email if any
          "emails": [...],
          "rating": 4.5,
          "reviews": 123,
          "price_range": "...",
          "status": "...",
          "latitude": 16.x,
          "longitude": 108.x,
          "google_maps_url": "...",
          "reviews_link": "...",
          "social": [...],           // detected social links / order links
          "menu": {...},
          "reservations": [...],
          "order_online": [...],
          "timezone": "Asia/Ho_Chi_Minh",
          "thumbnail": "..."
        },
        ...
      ]
    }

Usage:
    python normalize_results.py <raw-jsonl> [output-json]
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SOCIAL_HOSTS = (
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "linkedin.com",
    "pinterest.com",
    "tripadvisor.com",
    "zalo.me",
    "m.me",
    "messenger.com",
    "t.me",
    "telegram.org",
    "viber.com",
    "wa.me",
)

# Match a single email in free text.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Crude phone-digit sanitizer: keep digits and a leading +.
PHONE_RE = re.compile(r"[^\d+]")


def pick_email(entry: dict) -> tuple[str | None, list[str]]:
    """Return (primary_email, all_emails). Honors scraper's `emails` field
    and falls back to scanning website/description text for emails."""
    emails = entry.get("emails") or []
    emails = [e.strip() for e in emails if e and e.strip()]
    if not emails:
        text = " ".join(
            str(entry.get(k) or "")
            for k in ("web_site", "description", "title")
        )
        emails = EMAIL_RE.findall(text)
    # Deduplicate while preserving order.
    seen = set()
    uniq = []
    for e in emails:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return (uniq[0] if uniq else None), uniq


def internationalize_phone(phone: str | None, country_hint: str = "VN") -> str | None:
    """Return a tel:/wa.me friendly E.164-ish form.

    Vietnamese numbers frequently appear without the +84 prefix, e.g.
    '+84 387 979 043', '0236 123 4567', or '0901 234 567'.
    """
    if not phone:
        return None
    p = phone.strip()
    if not p:
        return None

    # Strip everything except digits.
    digits = re.sub(r"\D", "", p)
    if not digits:
        return None

    has_plus = p.startswith("+")

    if country_hint.upper() == "VN":
        if digits.startswith("0084"):
            digits = "84" + digits[4:]
        elif digits.startswith("84") and len(digits) > 9:
            pass  # already international
        elif digits.startswith("0"):
            digits = "84" + digits[1:]
    elif has_plus:
        # International non-VN: keep digits as-is (already has +).
        pass

    return "+" + digits


def wa_url(phone_e164: str | None) -> str | None:
    if not phone_e164:
        return None
    digits = re.sub(r"\D", "", phone_e164)
    return f"https://wa.me/{digits}" if digits else None


def mailto(email: str | None) -> str | None:
    return f"mailto:{email}" if email else None


def host_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except ValueError:
        return ""


def collect_social(entry: dict) -> list[dict]:
    """Pick up social / external links from website + order_online + reservations."""
    found: list[dict] = []
    candidates = []

    if entry.get("web_site"):
        candidates.append(("website", entry["web_site"]))

    for src in ("reservations", "order_online"):
        for item in entry.get(src) or []:
            link = (item or {}).get("link") if isinstance(item, dict) else None
            label = (item or {}).get("source") if isinstance(item, dict) else None
            if link:
                candidates.append((label or src, link))

    for label, link in candidates:
        host = host_of(link)
        if not host:
            continue
        kind = "social" if any(s in host for s in SOCIAL_HOSTS) else "external"
        found.append({"type": kind, "source": label or host, "url": link, "host": host})

    # Deduplicate by URL.
    seen = set()
    uniq = []
    for f in found:
        if f["url"] in seen:
            continue
        seen.add(f["url"])
        uniq.append(f)
    return uniq


def normalize_entry(entry: dict) -> dict:
    """Map one scraper Entry dict to the dashboard's flat schema."""
    phone_raw = entry.get("phone") or None
    phone_e164 = internationalize_phone(phone_raw)
    primary_email, all_emails = pick_email(entry)
    website = entry.get("web_site") or entry.get("website") or None

    latitude = entry.get("latitude")
    longitude = entry.get("longitude") or entry.get("longtitude")  # legacy typo

    return {
        "title": entry.get("title") or "",
        "category": entry.get("category") or "",
        "categories": entry.get("categories") or [],
        "address": entry.get("address") or "",
        "complete_address": entry.get("complete_address") or {},
        "phone": phone_raw,
        "phone_e164": phone_e164,
        "whatsapp_url": wa_url(phone_e164),
        "website": website,
        "email": primary_email,
        "emails": all_emails,
        "email_url": mailto(primary_email),
        "rating": entry.get("review_rating") or 0.0,
        "reviews": entry.get("review_count") or 0,
        "price_range": entry.get("price_range") or "",
        "status": entry.get("status") or "",
        "latitude": latitude,
        "longitude": longitude,
        "google_maps_url": entry.get("link") or "",
        "reviews_link": entry.get("reviews_link") or "",
        "social": collect_social(entry),
        "menu": entry.get("menu") or {},
        "reservations": entry.get("reservations") or [],
        "order_online": entry.get("order_online") or [],
        "timezone": entry.get("timezone") or "",
        "thumbnail": entry.get("thumbnail") or "",
        "plus_code": entry.get("plus_code") or "",
        "place_id": entry.get("place_id") or "",
        "cid": entry.get("cid") or "",
    }


def first_query(raw_lines: list[str]) -> str:
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        iid = obj.get("input_id") or ""
        # input_id is a uuid when no custom id was provided; otherwise it
        # often echoes the query. We can't recover the literal query here.
        return iid
    return ""


def summarize_missing(restaurants: list[dict]) -> dict:
    n = len(restaurants) or 1
    missing_phone = sum(1 for r in restaurants if not r["phone"])
    missing_website = sum(1 for r in restaurants if not r["website"])
    missing_email = sum(1 for r in restaurants if not r["email"])
    missing_rating = sum(1 for r in restaurants if not r["rating"])
    missing_coords = sum(
        1 for r in restaurants if r["latitude"] is None or r["longitude"] is None
    )
    return {
        "phone": {
            "missing_count": missing_phone,
            "missing_pct": round(100 * missing_phone / n, 1),
            "note": (
                "Google Maps does not always list a phone number; email "
                "extraction was not enabled in this run."
            ),
        },
        "website": {
            "missing_count": missing_website,
            "missing_pct": round(100 * missing_website / n, 1),
        },
        "email": {
            "missing_count": missing_email,
            "missing_pct": round(100 * missing_email / n, 1),
            "note": (
                "Emails require the scraper's -email flag (visits each "
                "website); not collected in this run."
            ),
        },
        "rating": {
            "missing_count": missing_rating,
            "missing_pct": round(100 * missing_rating / n, 1),
        },
        "coordinates": {
            "missing_count": missing_coords,
            "missing_pct": round(100 * missing_coords / n, 1),
        },
        "general": [
            "Email addresses are only available when the scraper is run with "
            "-email (it crawls each business website).",
            "Social profile URLs (Facebook/Instagram/etc.) are inferred from "
            "the website, reservations, and order_online fields; they are not "
            "a first-class Google Maps data point.",
            "Review text bodies (user_reviews) are dropped to keep the "
            "dashboard light; re-run with -extra-reviews if you need them.",
        ],
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    raw_path = Path(sys.argv[1]).resolve()
    if not raw_path.exists():
        print(f"Input file not found: {raw_path}")
        return 1

    out_path = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) >= 3
        else raw_path.with_name(raw_path.stem + "-normalized.json")
    )

    raw_lines = raw_path.read_text(encoding="utf-8").splitlines()
    restaurants: list[dict] = []
    for line_no, line in enumerate(raw_lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"warn: skipping line {line_no}: {exc}", file=sys.stderr)
            continue
        if not entry.get("title"):
            continue
        restaurants.append(normalize_entry(entry))

    payload = {
        "query": "restaurant in Da Nang, Vietnam",
        "source": str(raw_path.name),
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(restaurants),
        "missing": summarize_missing(restaurants),
        "restaurants": restaurants,
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"wrote {len(restaurants)} restaurants -> {out_path} "
        f"({out_path.stat().st_size} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
