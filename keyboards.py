"""
keyboards.py — Inline keyboard builders for HomeBot
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

RATINGS = [
    ("✦ Strong Contender", "STRONG"),
    ("◎ Okay",             "OKAY"),
    ("◌ KIV",              "KIV"),
    ("✕ No Go",            "NOGO"),
]

OWNERS = ["Michael", "Natalie", "Agent"]

EDIT_FIELDS = [
    ("📍 Location",            "address"),
    ("💰 Listed price (SGD)",  "rent_sgd"),
    ("📐 Floor size (sqft)",   "size_sqft"),
    ("🏢 Floor level",         "floor_level"),
    ("🚇 MRT",                 "mrt"),
    ("👤 Agent name",          "agent_name"),
    ("📞 Agent contact",       "agent_contact"),
]

def listing_picker(nicknames: list, action: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(n, callback_data=f"{action}:{n}")]
        for n in sorted(nicknames)
    ]
    return InlineKeyboardMarkup(buttons)

def rating_picker(nickname: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"set_rating:{nickname}:{code}")]
        for label, code in RATINGS
    ]
    return InlineKeyboardMarkup(buttons)

def owner_picker(nickname: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(o, callback_data=f"set_status_owner:{nickname}:{o}")]
        for o in OWNERS
    ]
    return InlineKeyboardMarkup(buttons)

def photo_note_prompt(nickname: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Yes, add a note",    callback_data=f"photo_note_yes:{nickname}"),
            InlineKeyboardButton("📐 Mark as floorplan",  callback_data=f"photo_floorplan:{nickname}"),
        ],
        [InlineKeyboardButton("✓ No, that's all",         callback_data=f"photo_note_no:{nickname}")],
    ])

def duplicate_picker(nickname: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("↩ Rename new entry",              callback_data=f"dup_rename:{nickname}"),
        InlineKeyboardButton("⇄ Reassign existing to new URL",  callback_data=f"dup_reassign:{nickname}"),
    ]])

def import_row_picker(row_index: int, nickname: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✓ Save",          callback_data=f"import_save:{row_index}"),
        InlineKeyboardButton("✕ Skip",          callback_data=f"import_skip:{row_index}"),
        InlineKeyboardButton("✎ Edit nickname", callback_data=f"import_rename:{row_index}"),
    ]])

def import_bulk_picker(total: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✓ Save all {total} listings", callback_data="import_save_all"),
        InlineKeyboardButton("Go one by one",                 callback_data="import_one_by_one"),
    ]])

def archive_confirm(nickname: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗂 Yes, archive", callback_data=f"archive_confirm:{nickname}"),
        InlineKeyboardButton("✕ Cancel",        callback_data="cancel"),
    ]])

def field_picker(nickname: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"edit_field:{nickname}:{field}")]
        for label, field in EDIT_FIELDS
    ]
    return InlineKeyboardMarkup(buttons)

def note_picker(notes: list, nickname: str) -> InlineKeyboardMarkup:
    """One button per note — tap to delete."""
    buttons = []
    for n in notes:
        preview = n.get("text") or "(photo only)"
        label   = f"{n['sender']}: {preview[:35]}{'…' if len(preview) > 35 else ''}"
        buttons.append([InlineKeyboardButton(
            f"🗑 {label}", callback_data=f"delete_note:{n['id']}:{nickname}"
        )])
    buttons.append([InlineKeyboardButton("✕ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def full_details_button(nickname: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Full details", callback_data=f"full_view:{nickname}"),
        InlineKeyboardButton("🤖 AI Summary",   callback_data=f"ai_summary:{nickname}"),
    ]])

def send_photos_button(nickname: str, count: int) -> InlineKeyboardMarkup:
    label = f"📎 View {count} photo{'s' if count != 1 else ''}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"send_photos:{nickname}"),
    ]])
