"""
scraper.py — Scrape listing data from PropertyGuru and 99.co
"""

import httpx
import re
from bs4 import BeautifulSoup
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-SG,en;q=0.9",
}

async def scrape_listing(url: str) -> dict:
    url = url.strip()
    if "propertyguru" in url:
        return await _scrape_propertyguru(url)
    elif "99.co" in url:
        return await _scrape_99co(url)
    else:
        return {"url": url, "_scrape_error": "Unrecognised listing site"}

async def _scrape_propertyguru(url: str) -> dict:
    data = {"url": url}
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("h1", class_=re.compile(r"title|listing-title", re.I))
        if title:
            data["address"] = title.get_text(strip=True)
        price = soup.find(class_=re.compile(r"price|listing-price", re.I))
        if price:
            raw = re.sub(r"[^\d]", "", price.get_text())
            if raw:
                data["rent_sgd"] = int(raw)
        body = soup.get_text()
        sqft = re.search(r"([\d,]+)\s*sq\s*ft", body, re.I)
        if sqft:
            data["size_sqft"] = int(sqft.group(1).replace(",", ""))
        floor = re.search(r"floor[:\s]+(\w+)", body, re.I)
        if floor:
            data["floor_level"] = floor.group(1)
        mrt = re.search(r"(\d+)\s*min(?:utes?)?\s+(?:walk\s+)?to\s+([\w\s]+MRT)", body, re.I)
        if mrt:
            data["mrt"] = f"{mrt.group(1)} min walk to {mrt.group(2).strip()}"
        agent = soup.find(class_=re.compile(r"agent-name|agent_name", re.I))
        if agent:
            data["agent_name"] = agent.get_text(strip=True)
    except Exception as e:
        data["_scrape_error"] = str(e)
    return data

async def _scrape_99co(url: str) -> dict:
    data = {"url": url}
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("h1")
        if title:
            data["address"] = title.get_text(strip=True)
        body = soup.get_text()
        price = re.search(r"\$\s*([\d,]+)\s*/\s*mo", body, re.I)
        if price:
            data["rent_sgd"] = int(price.group(1).replace(",", ""))
        sqft = re.search(r"([\d,]+)\s*sq\s*ft", body, re.I)
        if sqft:
            data["size_sqft"] = int(sqft.group(1).replace(",", ""))
        floor = re.search(r"floor[:\s]+(\w+)", body, re.I)
        if floor:
            data["floor_level"] = floor.group(1)
        mrt = re.search(r"(\d+)\s*min(?:utes?)?\s+(?:walk\s+)?to\s+([\w\s]+MRT)", body, re.I)
        if mrt:
            data["mrt"] = f"{mrt.group(1)} min walk to {mrt.group(2).strip()}"
        agent = soup.find(class_=re.compile(r"agent", re.I))
        if agent:
            data["agent_name"] = agent.get_text(strip=True)[:60]
    except Exception as e:
        data["_scrape_error"] = str(e)
    return data

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
