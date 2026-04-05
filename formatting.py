"""
formatting.py — Message formatters for HomeBot
"""

RATING_LABEL = {
    "STRONG":  "✦ Strong Contender",
    "OKAY":    "◎ Okay",
    "KIV":     "◌ KIV",
    "NOGO":    "✕ No Go",
    "UNRATED": "— Unrated",
}

RATING_EMOJI = {
    "STRONG":  "🟢",
    "OKAY":    "🟡",
    "KIV":     "🔵",
    "NOGO":    "🔴",
    "UNRATED": "⚪",
}

def format_summary_card(listing: dict, notes: list, media_count: int) -> str:
    nick   = listing["nickname"]
    rating = listing.get("rating", "UNRATED")
    lines  = [f"*{nick}*", f"{RATING_EMOJI[rating]} {RATING_LABEL[rating]}", ""]

    if listing.get("address"):    lines.append(f"📍 {listing['address']}")
    if listing.get("rent_sgd"):   lines.append(f"💰 SGD ${listing['rent_sgd']:,}/mo")
    if listing.get("size_sqft"):
        sz = f"📐 {listing['size_sqft']:,} sqft"
        if listing.get("floor_level"):
            sz += f"  ·  Floor {listing['floor_level']}"
        lines.append(sz)
    if listing.get("mrt"):        lines.append(f"🚇 {listing['mrt']}")
    if listing.get("agent_name"):
        agent = listing["agent_name"]
        if listing.get("agent_contact"):
            agent += f"  ·  {listing['agent_contact']}"
        lines.append(f"👤 {agent}")
    if media_count:               lines.append(f"📎 {media_count} photo{'s' if media_count != 1 else ''} attached")
    if listing.get("viewing_dt"): lines.append(f"📅 Viewing: {listing['viewing_dt']}")

    na_owner = listing.get("na_owner")
    na_desc  = listing.get("na_desc")
    na_due   = listing.get("na_due")
    if na_owner and na_desc:
        lines += ["", "⏭ *Next action*"]
        due_str = f"  ·  due {na_due}" if na_due else ""
        lines.append(f"→ {na_owner}:  {na_desc}{due_str}")

    if notes:
        lines += ["", "📝 *Notes*"]
        for n in notes:
            prefix = "📎 " if n.get("has_photo") else ""
            text   = n.get("text") or "(photo)"
            lines.append(f"*{n['sender']}*:  {prefix}{text}")

    return "\n".join(lines)

def format_details_list(listings: list) -> str:
    if not listings:
        return "No active listings yet. Add one with /add [url]"

    groups: dict = {}
    for l in listings:
        r = l.get("rating", "UNRATED")
        groups.setdefault(r, []).append(l)

    lines = ["*Your shortlist*", ""]
    for rating in ["STRONG", "OKAY", "KIV", "NOGO", "UNRATED"]:
        if rating not in groups:
            continue
        lines.append(f"{RATING_EMOJI[rating]} *{RATING_LABEL[rating]}*")
        for i, l in enumerate(groups[rating], 1):
            na = ""
            if l.get("na_owner") and l.get("na_desc"):
                na = f"  →  {l['na_owner']}: {l['na_desc']}"
                if l.get("na_due"):
                    na += f" ({l['na_due']})"
            lines.append(f"  {i}. {l['nickname']}{na}")
        lines.append("")

    lines.append("Tap a listing to view full details:")
    return "\n".join(lines)

def format_upcoming(listings: list) -> str:
    if not listings:
        return "No upcoming viewings scheduled.\n\nUse /edit to add a viewing date to a listing."
    lines = ["*Upcoming viewings*", ""]
    for l in listings:
        lines.append(f"📅 *{l['nickname']}*\n   {l['viewing_dt']}")
    return "\n".join(lines)

def format_import_preview(row: dict, index: int, total: int) -> str:
    lines = [f"*Row {index}/{total} — {row.get('nickname', 'Unknown')}*", ""]
    if row.get("address"):    lines.append(f"📍 {row['address']}")
    if row.get("rent_sgd"):   lines.append(f"💰 SGD ${int(row['rent_sgd']):,}/mo")
    if row.get("size_sqft"):  lines.append(f"📐 {row['size_sqft']} sqft")
    if row.get("mrt"):        lines.append(f"🚇 {row['mrt']}")
    if row.get("agent_name"): lines.append(f"👤 {row['agent_name']}")
    if row.get("rating") and row["rating"] != "UNRATED":
        lines.append(f"⭐ {RATING_LABEL.get(row['rating'], row['rating'])}")
    note_count = len(row.get("notes", []))
    if note_count:            lines.append(f"📝 {note_count} note{'s' if note_count != 1 else ''}")
    return "\n".join(lines)
