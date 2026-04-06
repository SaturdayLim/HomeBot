"""
database.py — SQLite schema + all data access functions for HomeBot
"""

import aiosqlite
import os
from typing import Optional

DB_PATH = os.getenv("DATABASE_PATH", "homebot.db")

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname    TEXT NOT NULL UNIQUE,
    url         TEXT,
    address     TEXT,
    rent_sgd    INTEGER,
    size_sqft   INTEGER,
    floor_level TEXT,
    mrt         TEXT,
    agent_name  TEXT,
    agent_contact TEXT,
    rating      TEXT DEFAULT 'UNRATED',
    viewing_dt  TEXT,
    status      TEXT DEFAULT 'ACTIVE',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id),
    text        TEXT,
    sender      TEXT NOT NULL,
    has_photo   INTEGER DEFAULT 0,
    photo_file_id TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL REFERENCES listings(id),
    telegram_file_id TEXT NOT NULL,
    media_type      TEXT DEFAULT 'PHOTO',
    caption         TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS next_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id),
    owner       TEXT NOT NULL,
    description TEXT NOT NULL,
    due_date    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS config (
    key         TEXT PRIMARY KEY,
    value       TEXT
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()

async def set_config(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_config(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM config WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def listing_exists(nickname: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM listings WHERE nickname = ? AND status != 'ARCHIVED'", (nickname,)
        ) as cur:
            return await cur.fetchone() is not None

async def save_listing(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO listings
              (nickname, url, address, rent_sgd, size_sqft, floor_level, mrt,
               agent_name, agent_contact, rating, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNRATED', 'ACTIVE')
        """, (
            data.get("nickname"), data.get("url"), data.get("address"),
            data.get("rent_sgd"), data.get("size_sqft"), data.get("floor_level"),
            data.get("mrt"), data.get("agent_name"), data.get("agent_contact"),
        ))
        await db.commit()
        return cur.lastrowid

async def reassign_listing(nickname: str, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE listings SET
              url=?, address=?, rent_sgd=?, size_sqft=?, floor_level=?,
              mrt=?, agent_name=?, agent_contact=?, updated_at=datetime('now')
            WHERE nickname=?
        """, (
            data.get("url"), data.get("address"), data.get("rent_sgd"),
            data.get("size_sqft"), data.get("floor_level"), data.get("mrt"),
            data.get("agent_name"), data.get("agent_contact"), nickname,
        ))
        await db.commit()

async def get_listing(nickname: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM listings WHERE nickname = ?", (nickname,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_active_listings() -> list[dict]:
    rating_order = "CASE rating WHEN 'STRONG' THEN 0 WHEN 'OKAY' THEN 1 WHEN 'KIV' THEN 2 WHEN 'NOGO' THEN 3 ELSE 4 END"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT l.*, na.owner as na_owner, na.description as na_desc, na.due_date as na_due
            FROM listings l
            LEFT JOIN next_actions na ON na.listing_id = l.id
              AND na.id = (SELECT id FROM next_actions WHERE listing_id = l.id ORDER BY created_at DESC LIMIT 1)
            WHERE l.status = 'ACTIVE'
            ORDER BY {rating_order}, na.due_date ASC NULLS LAST, l.created_at ASC
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def get_archived_listings() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM listings WHERE status = 'ARCHIVED' ORDER BY updated_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def update_listing_rating(nickname: str, rating: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE listings SET rating=?, updated_at=datetime('now') WHERE nickname=?",
            (rating, nickname)
        )
        await db.commit()

async def update_listing_viewing(nickname: str, viewing_dt: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE listings SET viewing_dt=?, updated_at=datetime('now') WHERE nickname=?",
            (viewing_dt, nickname)
        )
        await db.commit()

async def archive_listing(nickname: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE listings SET status='ARCHIVED', updated_at=datetime('now') WHERE nickname=?",
            (nickname,)
        )
        await db.commit()

async def restore_listing(nickname: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE listings SET status='ACTIVE', updated_at=datetime('now') WHERE nickname=?",
            (nickname,)
        )
        await db.commit()

async def get_upcoming_viewings() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM listings
            WHERE status = 'ACTIVE' AND viewing_dt IS NOT NULL AND viewing_dt >= datetime('now')
            ORDER BY viewing_dt ASC
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def add_note(nickname: str, text, sender: str, has_photo: bool = False, photo_file_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM listings WHERE nickname=?", (nickname,)) as cur:
            row = await cur.fetchone()
            if not row:
                return
            listing_id = row[0]
        await db.execute("""
            INSERT INTO notes (listing_id, text, sender, has_photo, photo_file_id)
            VALUES (?, ?, ?, ?, ?)
        """, (listing_id, text, sender, 1 if has_photo else 0, photo_file_id))
        await db.commit()

async def get_notes(nickname: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT n.* FROM notes n
            JOIN listings l ON l.id = n.listing_id
            WHERE l.nickname = ?
            ORDER BY n.created_at ASC
        """, (nickname,)) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def add_media(nickname: str, file_id: str, media_type: str = "PHOTO", caption: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM listings WHERE nickname=?", (nickname,)) as cur:
            row = await cur.fetchone()
            if not row:
                return
            listing_id = row[0]
        await db.execute(
            "INSERT INTO media (listing_id, telegram_file_id, media_type, caption) VALUES (?, ?, ?, ?)",
            (listing_id, file_id, media_type, caption)
        )
        await db.commit()

async def get_media_count(nickname: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM media m
            JOIN listings l ON l.id = m.listing_id
            WHERE l.nickname = ?
        """, (nickname,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def set_next_action(nickname: str, owner: str, description: str, due_date=None) -> Optional[int]:
    """Insert a next action and return its id, or None if listing not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM listings WHERE nickname=?", (nickname,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            listing_id = row[0]
        cur = await db.execute(
            "INSERT INTO next_actions (listing_id, owner, description, due_date) VALUES (?, ?, ?, ?)",
            (listing_id, owner, description, due_date)
        )
        await db.commit()
        return cur.lastrowid

async def get_asap_actions() -> list[dict]:
    """Return all active listings whose latest next action has due_date = 'ASAP'."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT l.nickname, na.id as action_id, na.owner, na.description
            FROM listings l
            JOIN next_actions na ON na.listing_id = l.id
              AND na.id = (SELECT id FROM next_actions WHERE listing_id = l.id ORDER BY created_at DESC LIMIT 1)
            WHERE l.status = 'ACTIVE' AND UPPER(na.due_date) = 'ASAP'
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def get_next_action(nickname: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT na.* FROM next_actions na
            JOIN listings l ON l.id = na.listing_id
            WHERE l.nickname = ?
            ORDER BY na.created_at DESC LIMIT 1
        """, (nickname,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

EDITABLE_FIELDS = frozenset({
    "address", "rent_sgd", "size_sqft", "floor_level",
    "mrt", "agent_name", "agent_contact",
})

async def update_listing_field(nickname: str, field: str, value):
    if field not in EDITABLE_FIELDS:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE listings SET {field}=?, updated_at=datetime('now') WHERE nickname=?",
            (value, nickname)
        )
        await db.commit()
