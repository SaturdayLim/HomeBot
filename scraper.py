"""
scraper.py — Scrape listing data from PropertyGuru and 99.co

Extraction order (each layer falls through to the next):
  1. JSON-LD  (<script type="application/ld+json">)
  2. Next.js  (<script id="__NEXT_DATA__">)
  3. Open Graph meta tags
  4. CSS / regex heuristics (original approach)
"""

import httpx
import json
import re
from bs4 import BeautifulSoup
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-SG,en-GB;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# ── Public entry point ────────────────────────────────────────────────────────

async def scrape_listing(url: str) -> dict:
    url = url.strip()
    if "propertyguru" in url:
        return await _scrape_propertyguru(url)
    elif "99.co" in url:
        return await _scrape_99co(url)
    else:
        return {"url": url, "_scrape_error": "Unrecognised listing site"}

# ── Shared helpers ────────────────────────────────────────────────────────────

def _extract_json_ld(soup: BeautifulSoup) -> dict:
    """Pull the first JSON-LD block that looks like a property listing."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(tag.string or "")
            # Could be a list or a single object
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                t = item.get("@type", "")
                if any(k in t for k in ("RealEstate", "Accommodation", "Apartment", "House", "Product")):
                    return item
            # Fallback: return first object if any found
            if items:
                return items[0]
        except Exception:
            pass
    return {}

def _extract_next_data(soup: BeautifulSoup) -> dict:
    """Pull Next.js page props from __NEXT_DATA__."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag:
        try:
            return json.loads(tag.string or "")
        except Exception:
            pass
    return {}

def _og(soup: BeautifulSoup, prop: str) -> Optional[str]:
    tag = soup.find("meta", property=f"og:{prop}") or soup.find("meta", attrs={"name": f"og:{prop}"})
    return tag["content"].strip() if tag and tag.get("content") else None

def _clean_int(raw: str) -> Optional[int]:
    cleaned = re.sub(r"[^\d]", "", raw)
    return int(cleaned) if cleaned else None

def _body_regex(body: str, data: dict):
    """Apply regex patterns to full page text. Fills missing fields only."""
    if "size_sqft" not in data:
        m = re.search(r"([\d,]+)\s*sq\s*ft", body, re.I)
        if m:
            data["size_sqft"] = int(m.group(1).replace(",", ""))
    if "floor_level" not in data:
        m = re.search(r"(?:floor|storey)[:\s#]+(\w+)", body, re.I)
        if m:
            data["floor_level"] = m.group(1)
    if "mrt" not in data:
        m = re.search(r"(\d+)\s*min(?:utes?)?\s+(?:walk\s+)?to\s+([\w\s]+MRT)", body, re.I)
        if m:
            data["mrt"] = f"{m.group(1)} min walk to {m.group(2).strip()}"

# ── PropertyGuru ──────────────────────────────────────────────────────────────

async def _scrape_propertyguru(url: str) -> dict:
    data = {"url": url}
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        body = soup.get_text(" ", strip=True)

        # ── Layer 1: JSON-LD ──
        ld = _extract_json_ld(soup)
        if ld:
            name = ld.get("name") or ld.get("address", {}).get("streetAddress")
            if name:
                data["address"] = name
            offers = ld.get("offers") or {}
            price  = offers.get("price") or ld.get("price")
            if price:
                v = _clean_int(str(price))
                if v:
                    data["rent_sgd"] = v
            floor_size = ld.get("floorSize") or ld.get("floorsize") or {}
            if isinstance(floor_size, dict):
                v = _clean_int(str(floor_size.get("value", "")))
                if v:
                    data["size_sqft"] = v

        # ── Layer 2: Next.js __NEXT_DATA__ ──
        if "rent_sgd" not in data or "address" not in data:
            nd = _extract_next_data(soup)
            # Walk into pageProps → listingDetails (structure varies by page version)
            props = nd.get("props", {}).get("pageProps", {})
            listing = (
                props.get("listingDetails")
                or props.get("listing")
                or props.get("data", {}).get("listing")
                or {}
            )
            if listing:
                if "address" not in data:
                    addr = listing.get("address") or listing.get("name") or listing.get("project_name")
                    if addr:
                        data["address"] = addr
                if "rent_sgd" not in data:
                    price = listing.get("price") or listing.get("asking_price")
                    if price:
                        v = _clean_int(str(price))
                        if v:
                            data["rent_sgd"] = v
                if "size_sqft" not in data:
                    size = listing.get("floor_area") or listing.get("floor_area_min")
                    if size:
                        v = _clean_int(str(size))
                        if v:
                            data["size_sqft"] = v
                if "floor_level" not in data:
                    fl = listing.get("floor_level") or listing.get("level")
                    if fl:
                        data["floor_level"] = str(fl)
                if "mrt" not in data:
                    mrt = listing.get("mrt_nearest") or listing.get("nearest_mrt")
                    if mrt:
                        data["mrt"] = mrt
                # Agent
                agent = listing.get("agent") or listing.get("listedBy") or {}
                if isinstance(agent, dict) and "agent_name" not in data:
                    name = agent.get("name") or agent.get("agent_name")
                    if name:
                        data["agent_name"] = name

        # ── Layer 3: Open Graph ──
        if "address" not in data:
            title = _og(soup, "title") or soup.title and soup.title.get_text(strip=True)
            if title:
                data["address"] = title

        # ── Layer 4: CSS / regex heuristics ──
        if "rent_sgd" not in data:
            price_el = soup.find(class_=re.compile(r"price|listing-price", re.I))
            if price_el:
                v = _clean_int(price_el.get_text())
                if v:
                    data["rent_sgd"] = v
        if "agent_name" not in data:
            agent_el = soup.find(class_=re.compile(r"agent[-_]?name", re.I))
            if agent_el:
                data["agent_name"] = agent_el.get_text(strip=True)
        _body_regex(body, data)

    except Exception as e:
        data["_scrape_error"] = str(e)

    return data

# ── 99.co ─────────────────────────────────────────────────────────────────────

async def _scrape_99co(url: str) -> dict:
    data = {"url": url}
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        body = soup.get_text(" ", strip=True)

        # ── Layer 1: JSON-LD ──
        ld = _extract_json_ld(soup)
        if ld:
            name = ld.get("name") or ld.get("address", {}).get("streetAddress")
            if name:
                data["address"] = name
            offers = ld.get("offers") or {}
            price  = offers.get("price") or ld.get("price")
            if price:
                v = _clean_int(str(price))
                if v:
                    data["rent_sgd"] = v
            fs = ld.get("floorSize") or {}
            if isinstance(fs, dict):
                v = _clean_int(str(fs.get("value", "")))
                if v:
                    data["size_sqft"] = v

        # ── Layer 2: Next.js __NEXT_DATA__ ──
        if "rent_sgd" not in data or "address" not in data:
            nd  = _extract_next_data(soup)
            props = nd.get("props", {}).get("pageProps", {})
            listing = (
                props.get("listing")
                or props.get("listingDetails")
                or props.get("data", {}).get("getListing")
                or {}
            )
            if listing:
                if "address" not in data:
                    addr = (listing.get("address_name")
                            or listing.get("address")
                            or listing.get("project", {}).get("name"))
                    if addr:
                        data["address"] = addr
                if "rent_sgd" not in data:
                    price = listing.get("price") or listing.get("asking_price_cents")
                    if price:
                        v = _clean_int(str(price))
                        # 99.co sometimes stores price in cents
                        if v and v > 100000:
                            v = v // 100
                        if v:
                            data["rent_sgd"] = v
                if "size_sqft" not in data:
                    size = listing.get("size_sqft") or listing.get("area")
                    if size:
                        v = _clean_int(str(size))
                        if v:
                            data["size_sqft"] = v
                if "floor_level" not in data:
                    fl = listing.get("floor_level") or listing.get("level")
                    if fl:
                        data["floor_level"] = str(fl)
                if "mrt" not in data:
                    mrt = listing.get("mrt_nearest") or listing.get("nearest_mrt")
                    if mrt:
                        data["mrt"] = mrt
                agent = listing.get("agent") or listing.get("user") or {}
                if isinstance(agent, dict) and "agent_name" not in data:
                    name = agent.get("name") or agent.get("display_name")
                    if name:
                        data["agent_name"] = name[:60]

        # ── Layer 3: Open Graph ──
        if "address" not in data:
            og_title = _og(soup, "title")
            if og_title:
                data["address"] = og_title
            elif soup.find("h1"):
                data["address"] = soup.find("h1").get_text(strip=True)

        # ── Layer 4: CSS / regex heuristics ──
        if "rent_sgd" not in data:
            m = re.search(r"\$\s*([\d,]+)\s*/\s*mo", body, re.I)
            if m:
                data["rent_sgd"] = int(m.group(1).replace(",", ""))
        if "agent_name" not in data:
            agent_el = soup.find(class_=re.compile(r"agent", re.I))
            if agent_el:
                data["agent_name"] = agent_el.get_text(strip=True)[:60]
        _body_regex(body, data)

    except Exception as e:
        data["_scrape_error"] = str(e)

    return data

# ── Formatter ─────────────────────────────────────────────────────────────────

def format_parsed_card(data: dict) -> str:
    lines = []
    if data.get("address"):    lines.append(f"📍 {data['address']}")
    if data.get("rent_sgd"):   lines.append(f"💰 SGD ${data['rent_sgd']:,}/mo")
    if data.get("size_sqft"):
        sz = f"📐 {data['size_sqft']:,} sqft"
        if data.get("floor_level"):
            sz += f"  ·  Floor {data['floor_level']}"
        lines.append(sz)
    if data.get("mrt"):        lines.append(f"🚇 {data['mrt']}")
    if data.get("agent_name"):
        agent = data["agent_name"]
        if data.get("agent_contact"):
            agent += f"  ·  {data['agent_contact']}"
        lines.append(f"👤 {agent}")
    if not lines:
        lines.append("(Could not parse listing details — fill in manually via /edit)")
    if data.get("_scrape_error"):
        lines.append(f"\n⚠️ Partial parse — site may have blocked the request.")
    return "\n".join(lines)
