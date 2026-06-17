#!/usr/bin/env python3
"""Validate and enrich restaurant contacts from normalized scraper JSON.

Checks phone numbers, WhatsApp, Zalo, Messenger, Telegram, Viber, email,
and website availability.  Produces an "enriched" JSON that the dashboard
builder consumes.

Usage:
    python validate_contacts.py <normalized.json> [output-enriched.json]

Channels validated:
    - Phone  (format / length heuristics)
    - WhatsApp  (wa.me link check, HTTP HEAD)
    - Zalo  (zalo.me link check, HTTP HEAD)
    - Facebook Messenger  (messenger link from social data)
    - Telegram  (t.me link from social data)
    - Viber  (viber link or phone-based)
    - Email  (format check, SMTP MX lookup optional)
    - Website  (HTTP HEAD)

Status values per channel:  valid | invalid | unknown
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

HEAD_TIMEOUT = 8  # seconds per HTTP check
BATCH_SIZE = 20  # concurrent checks per batch
BATCH_DELAY = 1.0  # seconds between batches to be polite

SOCIAL_HOSTS_MAP = {
    "facebook.com": "facebook",
    "messenger.com": "messenger",
    "m.me": "messenger",
    "t.me": "telegram",
    "telegram.org": "telegram",
    "zalo.me": "zalo",
    "viber.com": "viber",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "linkedin.com": "linkedin",
    "tripadvisor.com": "tripadvisor",
    "pinterest.com": "pinterest",
}

# Vietnamese phone patterns (after E.164 normalization)
VN_MOBILE_PREFIXES = (
    "32", "33", "34", "35", "36", "37", "38", "39",  # Viettel
    "52", "53", "54", "55", "56", "57", "58", "59",  # Vinaphone / MobiFone
    "70", "76", "77", "78", "79",                      # MobiFone
    "81", "82", "83", "84", "85", "86",               # Vinaphone
    "88", "89",                                        # MobiFone
    "56", "57", "58", "59",                            # Wintel
    "90", "91", "92", "93", "94", "95", "96", "97", "98",  # Vietnamobile
    "99",                                              # Gmobile
)

PHONE_RE = re.compile(r"[^\d+]")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


# ---------------------------------------------------------------------------
# Phone validation
# ---------------------------------------------------------------------------

def is_valid_vn_phone(digits: str) -> bool:
    """Check if digits (with country code) look like a valid VN mobile."""
    if digits.startswith("84") and len(digits) == 12:
        prefix = digits[2:4]
        return prefix in VN_MOBILE_PREFIXES
    # Landline: 0236, 0238, 0250 etc -> 84236, 84238, 84250
    if digits.startswith("84") and len(digits) in (11, 12):
        return True  # accept landlines
    return False


def validate_phone(phone: str | None, phone_e164: str | None) -> dict[str, Any]:
    """Return phone_valid status and details."""
    if not phone_e164:
        return {"phone_valid": False, "phone_digits": None}

    digits = re.sub(r"\D", "", phone_e164)
    if not digits or len(digits) < 10:
        return {"phone_valid": False, "phone_digits": digits}

    # Vietnam-specific check
    if digits.startswith("84"):
        valid = is_valid_vn_phone(digits)
    elif digits.startswith("1") and len(digits) == 11:
        valid = True  # US number, accept
    else:
        # Generic: 8-15 digits
        valid = 10 <= len(digits) <= 15

    return {"phone_valid": valid, "phone_digits": digits}


# ---------------------------------------------------------------------------
# Link detection from social / reservation / order_online data
# ---------------------------------------------------------------------------

def extract_messenger_links(entry: dict) -> list[str]:
    """Find Facebook/Messenger links."""
    urls = []
    # Check social links
    for s in entry.get("social") or []:
        host = (s.get("host") or "").lower()
        url = s.get("url") or ""
        if any(h in host for h in ("facebook.com", "m.me", "messenger.com")):
            urls.append(url)
    # Check about / serve links
    for src in ("reservations", "order_online"):
        for item in entry.get(src) or []:
            link = (item or {}).get("link") or ""
            host = (urlparse(link).hostname or "").lower()
            if any(h in host for h in ("facebook.com", "m.me", "messenger.com")):
                urls.append(link)
    return urls


def extract_telegram_links(entry: dict) -> list[str]:
    urls = []
    for s in entry.get("social") or []:
        host = (s.get("host") or "").lower()
        url = s.get("url") or ""
        if "t.me" in host or "telegram" in host:
            urls.append(url)
    for src in ("reservations", "order_online"):
        for item in entry.get(src) or []:
            link = (item or {}).get("link") or ""
            host = (urlparse(link).hostname or "").lower()
            if "t.me" in host or "telegram" in host:
                urls.append(link)
    return urls


def extract_zalo_links(entry: dict) -> list[str]:
    urls = []
    for s in entry.get("social") or []:
        host = (s.get("host") or "").lower()
        url = s.get("url") or ""
        if "zalo" in host or "zalo.me" in url:
            urls.append(url)
    for src in ("reservations", "order_online"):
        for item in entry.get(src) or []:
            link = (item or {}).get("link") or ""
            if "zalo" in link.lower():
                urls.append(link)
    # Also check website text
    website = entry.get("website") or ""
    if "zalo" in website.lower():
        urls.append(website)
    return urls


def extract_viber_links(entry: dict) -> list[str]:
    urls = []
    for s in entry.get("social") or []:
        host = (s.get("host") or "").lower()
        url = s.get("url") or ""
        if "viber" in host or "viber" in url.lower():
            urls.append(url)
    for src in ("reservations", "order_online"):
        for item in entry.get(src) or []:
            link = (item or {}).get("link") or ""
            if "viber" in link.lower():
                urls.append(link)
    return urls


# ---------------------------------------------------------------------------
# Async HTTP validation
# ---------------------------------------------------------------------------

async def check_url(session: Any, url: str, timeout: float = HEAD_TIMEOUT) -> str:
    """HEAD-check a URL.  Returns 'valid', 'invalid', or 'unknown'."""
    import aiohttp

    try:
        # Clean URL: unwrap Google redirect wrappers
        if "/url?q=" in url:
            # Try to extract the real URL
            parsed = urlparse(url)
            qs = parsed.query
            for part in qs.split("&"):
                if part.startswith("q="):
                    url = part[2:]
                    break

        async with session.head(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            ssl=False,
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            if 200 <= resp.status < 400:
                # Extra check for WhatsApp: if the page title or redirect
                # indicates the number doesn't exist
                final_url = str(resp.url)
                # wa.me redirects to web.whatsapp.com for valid numbers
                if "wa.me" in url:
                    if "web.whatsapp.com" in final_url or "wa.me" in final_url:
                        return "valid"
                # zalo.me valid pages return 200
                if "zalo.me" in url:
                    return "valid"
                return "valid"
            elif resp.status in (404, 410):
                return "invalid"
            else:
                # 403, 500, etc. - inconclusive
                return "unknown"
    except asyncio.TimeoutError:
        return "unknown"
    except Exception:
        return "unknown"


async def check_url_get(session: Any, url: str, timeout: float = HEAD_TIMEOUT) -> tuple[str, str]:
    """GET-check a URL, return (status, redirect_url)."""
    import aiohttp

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            ssl=False,
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            return ("valid", str(resp.url))
    except Exception:
        return ("unknown", "")


async def validate_whatsapp(
    session: Any, phone_e164: str | None, phone_digits: str | None, entry: dict
) -> dict[str, Any]:
    """Validate WhatsApp presence."""
    result: dict[str, Any] = {
        "whatsapp_status": "unknown",
        "whatsapp_url": None,
        "whatsapp_verified": False,
    }

    if not phone_digits:
        return result

    wa_url = f"https://wa.me/{phone_digits}"
    result["whatsapp_url"] = wa_url

    # Check if there's an explicit wa.me link in their social/reservation data
    has_wa_link = False
    for s in entry.get("social") or []:
        host = (s.get("host") or "").lower()
        if "wa.me" in host:
            has_wa_link = True
            break
    if not has_wa_link:
        for src in ("reservations", "order_online"):
            for item in entry.get(src) or []:
                link = (item or {}).get("link") or ""
                if "wa.me" in link.lower():
                    has_wa_link = True
                    break
            if has_wa_link:
                break

    if has_wa_link:
        # They explicitly advertise WhatsApp - check the direct number link
        status = await check_url(session, wa_url)
        result["whatsapp_status"] = status
        result["whatsapp_verified"] = status == "valid"
    else:
        # No explicit WA link - do a quick check
        status = await check_url(session, wa_url)
        result["whatsapp_status"] = status
        result["whatsapp_verified"] = status == "valid"

    return result


async def validate_zalo(
    session: Any, entry: dict, phone_digits: str | None
) -> dict[str, Any]:
    """Validate Zalo presence."""
    result: dict[str, Any] = {
        "zalo_status": "unknown",
        "zalo_url": None,
        "zalo_verified": False,
    }

    zalo_links = extract_zalo_links(entry)
    if not zalo_links:
        # Try constructing zalo.me from phone number
        if phone_digits and len(phone_digits) >= 10:
            zalo_url = f"https://zalo.me/{phone_digits}"
            zalo_links.append(zalo_url)

    if zalo_links:
        url = zalo_links[0]
        result["zalo_url"] = url
        status = await check_url(session, url)
        result["zalo_status"] = status
        result["zalo_verified"] = status == "valid"

    return result


async def validate_messenger(session: Any, entry: dict) -> dict[str, Any]:
    """Validate Facebook Messenger presence."""
    result: dict[str, Any] = {
        "messenger_status": "unknown",
        "messenger_url": None,
        "messenger_verified": False,
    }

    links = extract_messenger_links(entry)
    if links:
        url = links[0]
        # Convert facebook.com page to messenger link if possible
        if "facebook.com" in url and "m.me" not in url:
            # Can't reliably convert, keep original
            pass
        result["messenger_url"] = url
        status = await check_url(session, url)
        result["messenger_status"] = status
        result["messenger_verified"] = status == "valid"

    return result


async def validate_telegram(session: Any, entry: dict) -> dict[str, Any]:
    """Validate Telegram presence."""
    result: dict[str, Any] = {
        "telegram_status": "unknown",
        "telegram_url": None,
        "telegram_verified": False,
    }

    links = extract_telegram_links(entry)
    if links:
        url = links[0]
        result["telegram_url"] = url
        status = await check_url(session, url)
        result["telegram_status"] = status
        result["telegram_verified"] = status == "valid"

    return result


async def validate_viber(session: Any, entry: dict) -> dict[str, Any]:
    """Validate Viber presence."""
    result: dict[str, Any] = {
        "viber_status": "unknown",
        "viber_url": None,
        "viber_verified": False,
    }

    links = extract_viber_links(entry)
    if links:
        url = links[0]
        result["viber_url"] = url
        status = await check_url(session, url)
        result["viber_status"] = status
        result["viber_verified"] = status == "valid"

    return result


async def validate_email(email: str | None) -> dict[str, Any]:
    """Basic email format validation. MX check optional."""
    result: dict[str, Any] = {
        "email_valid": False,
        "email_status": "unknown",
    }

    if not email:
        return result

    # Format check
    if EMAIL_RE.fullmatch(email):
        result["email_valid"] = True
        result["email_status"] = "valid"

        # Optional: MX record check
        domain = email.split("@")[-1]
        try:
            records = await asyncio.get_event_loop().run_in_executor(
                None, lambda: socket.getaddrinfo(domain, 0, socket.AF_INET, socket.SOCK_STREAM)
            )
            if records:
                result["email_status"] = "valid"
        except Exception:
            result["email_status"] = "unknown"  # valid format but can't verify

    else:
        result["email_status"] = "invalid"

    return result


async def validate_website(session: Any, website: str | None) -> dict[str, Any]:
    """Check if website is reachable."""
    result: dict[str, Any] = {
        "website_status": "unknown",
        "website_reachable": False,
    }

    if not website:
        return result

    status = await check_url(session, website)
    result["website_status"] = status
    result["website_reachable"] = status == "valid"

    return result


# ---------------------------------------------------------------------------
# Process one restaurant
# ---------------------------------------------------------------------------

async def validate_entry(
    session: Any, entry: dict, idx: int, total: int
) -> dict[str, Any]:
    """Enrich one restaurant entry with validation results."""
    phone_raw = entry.get("phone")
    phone_e164 = entry.get("phone_e164")
    email = entry.get("email")
    website = entry.get("website")

    print(
        f"  [{idx+1}/{total}] Validating: {(entry.get('title') or '?')[:60]}",
        file=sys.stderr,
    )

    # Phone validation (sync)
    phone_info = validate_phone(phone_raw, phone_e164)
    phone_digits = phone_info.get("phone_digits")

    # WhatsApp
    wa_info = await validate_whatsapp(session, phone_e164, phone_digits, entry)

    # Zalo
    zalo_info = await validate_zalo(session, entry, phone_digits)

    # Messenger
    msg_info = await validate_messenger(session, entry)

    # Telegram
    tg_info = await validate_telegram(session, entry)

    # Viber
    viber_info = await validate_viber(session, entry)

    # Email
    em_info = await validate_email(email)

    # Website
    ws_info = await validate_website(session, website)

    # Enriched entry
    enriched = dict(entry)
    enriched.update(phone_info)
    enriched.update(wa_info)
    enriched.update(zalo_info)
    enriched.update(msg_info)
    enriched.update(tg_info)
    enriched.update(viber_info)
    enriched.update(em_info)
    enriched.update(ws_info)

    return enriched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_validate(data: dict) -> dict:
    """Validate all restaurants in parallel with rate limiting."""
    import aiohttp

    restaurants = data.get("restaurants") or []
    total = len(restaurants)
    print(f"Validating {total} restaurants...", file=sys.stderr)

    connector = aiohttp.TCPConnector(limit=BATCH_SIZE, ssl=False)
    enriched_restaurants: list[dict] = []

    async with aiohttp.ClientSession(connector=connector) as session:
        # Process in batches to be polite
        for batch_start in range(0, total, BATCH_SIZE):
            batch = restaurants[batch_start : batch_start + BATCH_SIZE]
            tasks = [
                validate_entry(session, r, batch_start + i, total)
                for i, r in enumerate(batch)
            ]
            results = await asyncio.gather(*tasks)
            enriched_restaurants.extend(results)

            if batch_start + BATCH_SIZE < total:
                print(
                    f"  (batch {batch_start//BATCH_SIZE + 1}, "
                    f"waiting {BATCH_DELAY}s...)",
                    file=sys.stderr,
                )
                await asyncio.sleep(BATCH_DELAY)

    # Build enriched payload
    enriched = dict(data)
    enriched["restaurants"] = enriched_restaurants
    enriched["validated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # Compute summary stats
    enriched["validation_summary"] = compute_summary(enriched_restaurants)

    return enriched


def compute_summary(restaurants: list[dict]) -> dict[str, Any]:
    """Compute validation statistics."""
    n = len(restaurants) or 1
    phone_valid = sum(1 for r in restaurants if r.get("phone_valid"))
    wa_valid = sum(1 for r in restaurants if r.get("whatsapp_status") == "valid")
    wa_invalid = sum(1 for r in restaurants if r.get("whatsapp_status") == "invalid")
    wa_unknown = sum(1 for r in restaurants if r.get("whatsapp_status") == "unknown")
    zalo_valid = sum(1 for r in restaurants if r.get("zalo_status") == "valid")
    zalo_invalid = sum(1 for r in restaurants if r.get("zalo_status") == "invalid")
    zalo_unknown = sum(1 for r in restaurants if r.get("zalo_status") == "unknown")
    msg_valid = sum(1 for r in restaurants if r.get("messenger_status") == "valid")
    msg_unknown = sum(1 for r in restaurants if r.get("messenger_status") == "unknown")
    tg_valid = sum(1 for r in restaurants if r.get("telegram_status") == "valid")
    tg_unknown = sum(1 for r in restaurants if r.get("telegram_status") == "unknown")
    viber_valid = sum(1 for r in restaurants if r.get("viber_status") == "valid")
    viber_unknown = sum(1 for r in restaurants if r.get("viber_status") == "unknown")
    email_valid = sum(1 for r in restaurants if r.get("email_status") == "valid")
    ws_valid = sum(1 for r in restaurants if r.get("website_status") == "valid")

    return {
        "total": len(restaurants),
        "phone_valid": phone_valid,
        "whatsapp": {"valid": wa_valid, "invalid": wa_invalid, "unknown": wa_unknown},
        "zalo": {"valid": zalo_valid, "invalid": zalo_invalid, "unknown": zalo_unknown},
        "messenger": {"valid": msg_valid, "unknown": msg_unknown},
        "telegram": {"valid": tg_valid, "unknown": tg_unknown},
        "viber": {"valid": viber_valid, "unknown": viber_unknown},
        "email": {"valid": email_valid},
        "website": {"reachable": ws_valid},
    }


def main() -> int:
    try:
        import aiohttp
    except ImportError:
        print(
            "ERROR: aiohttp is required. Install with: pip install aiohttp",
            file=sys.stderr,
        )
        return 1

    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    json_path = Path(sys.argv[1]).resolve()
    if not json_path.exists():
        print(f"File not found: {json_path}", file=sys.stderr)
        return 1

    out_path = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) >= 3
        else json_path.with_name(
            json_path.stem.replace("-normalized", "") + "-enriched.json"
        )
    )

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    enriched = asyncio.run(run_validate(data))

    out_path.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = enriched.get("validation_summary", {})
    print("\n=== Validation Summary ===", file=sys.stderr)
    print(f"  Total restaurants:  {summary.get('total', 0)}", file=sys.stderr)
    print(f"  Phone valid:         {summary.get('phone_valid', 0)}", file=sys.stderr)
    wa = summary.get("whatsapp", {})
    print(
        f"  WhatsApp:            valid={wa.get('valid',0)} invalid={wa.get('invalid',0)} unknown={wa.get('unknown',0)}",
        file=sys.stderr,
    )
    za = summary.get("zalo", {})
    print(
        f"  Zalo:                valid={za.get('valid',0)} invalid={za.get('invalid',0)} unknown={za.get('unknown',0)}",
        file=sys.stderr,
    )
    ms = summary.get("messenger", {})
    print(
        f"  Messenger:           valid={ms.get('valid',0)} unknown={ms.get('unknown',0)}",
        file=sys.stderr,
    )
    tg = summary.get("telegram", {})
    print(
        f"  Telegram:            valid={tg.get('valid',0)} unknown={tg.get('unknown',0)}",
        file=sys.stderr,
    )
    vb = summary.get("viber", {})
    print(
        f"  Viber:              valid={vb.get('valid',0)} unknown={vb.get('unknown',0)}",
        file=sys.stderr,
    )
    print(
        f"  Email:              valid={summary.get('email', {}).get('valid', 0)}",
        file=sys.stderr,
    )
    print(
        f"  Website:            reachable={summary.get('website', {}).get('reachable', 0)}",
        file=sys.stderr,
    )

    size = out_path.stat().st_size
    print(
        f"\nwrote {len(enriched.get('restaurants', []))} enriched restaurants -> {out_path} ({size:,} bytes)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
