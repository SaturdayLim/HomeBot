"""
importer.py — CSV template generation and bulk import logic
"""

import csv
import io

TEMPLATE_COLUMNS = [
    "nickname", "url", "address", "rent_sgd", "size_sqft",
    "floor_level", "mrt", "agent_name", "agent_contact",
    "rating", "next_action_owner", "next_action_desc",
    "next_action_due", "notes",
]

TEMPLATE_EXAMPLE = {
    "nickname": "Tiong Bahru 2BR",
    "url": "https://www.propertyguru.com.sg/listing/...",
    "address": "18 Tiong Bahru Rd, #08-12",
    "rent_sgd": "3200",
    "size_sqft": "710",
    "floor_level": "8",
    "mrt": "4 min walk to Tiong Bahru MRT",
    "agent_name": "James Lim",
    "agent_contact": "+65 9123 4567",
    "rating": "STRONG",
    "next_action_owner": "Agent",
    "next_action_desc": "Confirm lease start date",
    "next_action_due": "10 Apr",
    "notes": "Great natural light | kitchen small | Natalie loves the area",
}

VALID_RATINGS = {"STRONG", "OKAY", "KIV", "NOGO", "UNRATED", ""}
VALID_OWNERS  = {"Michael", "Natalie", "Agent", ""}

def generate_template_csv() -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=TEMPLATE_COLUMNS)
    writer.writeheader()
    writer.writerow(TEMPLATE_EXAMPLE)
    writer.writerow({c: "" for c in TEMPLATE_COLUMNS})
    writer.writerow({c: "" for c in TEMPLATE_COLUMNS})
    return output.getvalue().encode("utf-8")

def parse_import_csv(raw_bytes: bytes) -> tuple:
    rows, errors = [], []
    try:
        text   = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        return [], [f"Could not read file: {e}"]

    for i, row in enumerate(reader, start=2):
        if not any(row.values()):
            continue
        nick = row.get("nickname", "").strip()
        if not nick:
            errors.append(f"Row {i}: missing nickname — skipped")
            continue

        rating = row.get("rating", "").strip().upper()
        if rating not in VALID_RATINGS:
            errors.append(f"Row {i} ({nick}): invalid rating '{rating}' — defaulting to UNRATED")
            rating = "UNRATED"
        if not rating:
            rating = "UNRATED"

        owner = row.get("next_action_owner", "").strip()
        if owner and owner not in VALID_OWNERS:
            errors.append(f"Row {i} ({nick}): unknown owner '{owner}' — skipping next action")
            owner = ""

        rent = None
        try:
            raw_rent = row.get("rent_sgd", "").strip().replace(",", "")
            if raw_rent:
                rent = int(float(raw_rent))
        except ValueError:
            errors.append(f"Row {i} ({nick}): invalid rent — ignored")

        size = None
        try:
            raw_size = row.get("size_sqft", "").strip().replace(",", "")
            if raw_size:
                size = int(float(raw_size))
        except ValueError:
            errors.append(f"Row {i} ({nick}): invalid size — ignored")

        raw_notes = row.get("notes", "").strip()
        notes = [n.strip() for n in raw_notes.split("|") if n.strip()] if raw_notes else []

        rows.append({
            "nickname":          nick,
            "url":               row.get("url", "").strip() or None,
            "address":           row.get("address", "").strip() or None,
            "rent_sgd":          rent,
            "size_sqft":         size,
            "floor_level":       row.get("floor_level", "").strip() or None,
            "mrt":               row.get("mrt", "").strip() or None,
            "agent_name":        row.get("agent_name", "").strip() or None,
            "agent_contact":     row.get("agent_contact", "").strip() or None,
            "rating":            rating,
            "next_action_owner": owner or None,
            "next_action_desc":  row.get("next_action_desc", "").strip() or None,
            "next_action_due":   row.get("next_action_due", "").strip() or None,
            "notes":             notes,
        })
    return rows, errors
