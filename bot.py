"""
bot.py — HomeBot: Rental tracker for Michael & Natalie
"""

import os
import io
import re
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

import database as db
import keyboards as kb
import formatting as fmt
from scraper import scrape_listing, format_parsed_card
from importer import generate_template_csv, parse_import_csv
import reminders

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN      = os.getenv("BOT_TOKEN")
MICHAEL_ID     = int(os.getenv("MICHAEL_TELEGRAM_ID", "0"))
NATALIE_ID_STR = os.getenv("NATALIE_TELEGRAM_ID", "REPLACE_ME")
NATALIE_ID     = int(NATALIE_ID_STR) if NATALIE_ID_STR.isdigit() else None

AWAIT_NICKNAME      = "await_nickname"
AWAIT_STATUS_DESC   = "await_status_desc"
AWAIT_STATUS_DATE   = "await_status_date"
AWAIT_PHOTO_NOTE    = "await_photo_note"
AWAIT_IMPORT_RENAME = "await_import_rename"
AWAIT_EDIT_VALUE    = "await_edit_value"

def sender_name(update: Update) -> str:
    uid = update.effective_user.id
    if uid == MICHAEL_ID:                return "Michael"
    if NATALIE_ID and uid == NATALIE_ID: return "Natalie"
    return update.effective_user.first_name or "Unknown"

async def active_nicknames() -> list:
    listings = await db.get_active_listings()
    return sorted(l["nickname"] for l in listings)

async def reply(update: Update, text: str, keyboard=None, parse_mode=ParseMode.MARKDOWN):
    await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode=parse_mode)

async def edit_or_reply(update: Update, text: str, keyboard=None):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.callback_query.message.reply_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await reply(update, text, keyboard)

# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_config("GROUP_CHAT_ID", str(update.effective_chat.id))
    await reply(update,
        "🏠 *HomeBot* is live!\n\n"
        "• `/add [url]` — add a listing\n"
        "• `/import` — bulk import via CSV\n"
        "• `/details` — view shortlist\n"
        "• `/help` — all commands\n\n"
        "Send a 📷 photo anytime to attach it to a listing."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "*HomeBot commands*\n\n"
        "`/add [url]` — add a listing (or multi-line with all fields)\n"
        "`/import` — bulk import via CSV\n"
        "`/details` — view shortlist\n"
        "`/edit` — edit a listing's fields\n"
        "`/note [text]` — add a note\n"
        "`/rate` — rate a listing\n"
        "`/status` — set next action\n"
        "`/upcoming` — viewing appointments\n"
        "`/archive` — hide a listing\n"
        "`/archived` — view archived listings\n"
        "`/restore [name]` — recover archived listing\n"
        "`/media [name]` — check photos\n"
        "`/import` — bulk import via CSV"
    )

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Parse multi-line message:
    #   /add [url]        ← url optional on first line or second line
    #   [location]
    #   [price SGD]
    #   [sqft]
    #   [mrt]
    #   [agent name, contact]
    full_text = update.message.text or ""
    lines = [l.strip() for l in full_text.split("\n")]

    # Pull URL from first line remainder or second line
    first_parts = lines[0].split(None, 1)
    rest = first_parts[1] if len(first_parts) > 1 else ""
    url, pos_start = None, 1
    if rest.startswith("http"):
        url, pos_start = rest, 1
    elif len(lines) > 1 and lines[1].startswith("http"):
        url, pos_start = lines[1], 2

    # Collect up to 5 positional fields
    raw = (lines[pos_start:pos_start + 5] + [""] * 5)[:5]
    loc_raw, price_raw, sqft_raw, mrt_raw, agent_raw = raw

    manual = {}
    if loc_raw and loc_raw != "-":
        manual["address"] = loc_raw
    if price_raw and price_raw != "-":
        digits = re.sub(r"[^\d]", "", price_raw)
        if digits:
            manual["rent_sgd"] = int(digits)
    if sqft_raw and sqft_raw != "-":
        digits = re.sub(r"[^\d]", "", sqft_raw)
        if digits:
            manual["size_sqft"] = int(digits)
    if mrt_raw and mrt_raw != "-":
        manual["mrt"] = mrt_raw
    if agent_raw and agent_raw != "-":
        parts = agent_raw.split(",", 1)
        manual["agent_name"] = parts[0].strip()
        if len(parts) > 1:
            manual["agent_contact"] = parts[1].strip()

    if not url and not manual:
        await reply(update,
            "*Add a listing*\n\n"
            "URL only:\n`/add https://propertyguru.com.sg/...`\n\n"
            "With details (any line can be blank or `-` to skip):\n"
            "`/add [url or blank]`\n"
            "`[location]`\n"
            "`[price SGD]`\n"
            "`[sqft]`\n"
            "`[mrt distance]`\n"
            "`[agent name, contact]`")
        return

    if url:
        await reply(update, "🔍 Parsing listing...")
        data = await scrape_listing(url)
    else:
        data = {}

    data.update(manual)  # manual fields override scraped data
    card = format_parsed_card(data)
    context.user_data["pending_listing"] = data
    context.user_data["state"]           = AWAIT_NICKNAME
    await reply(update, f"*Listing details:*\n\n{card}\n\nWhat nickname do you want to save this as?")

async def cmd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    listings = await db.get_active_listings()
    if not listings:
        await reply(update, "No active listings yet. Use `/add [url]` to add one.")
        return
    text  = fmt.format_details_list(listings)
    nicks = [l["nickname"] for l in listings]
    await reply(update, text, kb.listing_picker(nicks, "view_listing"))

async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nicks = await active_nicknames()
    if not nicks:
        await reply(update, "No listings saved yet. Use `/add` first."); return
    text = " ".join(context.args).strip()
    if not text:
        await reply(update, "Include your note after the command.\nE.g. `/note great natural light`"); return
    context.user_data["pending_note"] = text
    await reply(update, "Which listing is this note for?", kb.listing_picker(nicks, "note_listing"))

async def cmd_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nicks = await active_nicknames()
    if not nicks:
        await reply(update, "No listings saved yet."); return
    await reply(update, "Which listing are you rating?", kb.listing_picker(nicks, "rate_listing"))

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nicks = await active_nicknames()
    if not nicks:
        await reply(update, "No listings saved yet."); return
    await reply(update, "Which listing do you want to set a next action for?",
                kb.listing_picker(nicks, "status_listing"))

async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    listings = await db.get_upcoming_viewings()
    await reply(update, fmt.format_upcoming(listings))

async def cmd_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nicks = await active_nicknames()
    if not nicks:
        await reply(update, "No active listings to archive."); return
    await reply(update, "Which listing do you want to archive?",
                kb.listing_picker(nicks, "archive_listing"))

async def cmd_archived(update: Update, context: ContextTypes.DEFAULT_TYPE):
    listings = await db.get_archived_listings()
    if not listings:
        await reply(update, "No archived listings."); return
    names = "\n".join(f"• {l['nickname']}" for l in listings)
    await reply(update, f"🗂 *Archived listings*\n\n{names}\n\nUse `/restore [name]` to recover one.")

async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = " ".join(context.args).strip()
    if not nick:
        listings = await db.get_archived_listings()
        if not listings:
            await reply(update, "No archived listings."); return
        await reply(update, "Which listing do you want to restore?",
                    kb.listing_picker([l["nickname"] for l in listings], "restore_listing"))
        return
    listing = await db.get_listing(nick)
    if not listing or listing["status"] != "ARCHIVED":
        await reply(update, f"'{nick}' not found in archives."); return
    await db.restore_listing(nick)
    await reply(update, f"✓ *{nick}* restored to your active listings.")

async def cmd_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = " ".join(context.args).strip()
    if not nick:
        await reply(update, "Usage: `/media [listing name]`"); return
    count = await db.get_media_count(nick)
    if count == 0:
        await reply(update, f"No media attached to *{nick}* yet.\nSend a photo and I'll ask which listing it's for.")
    else:
        await reply(update, f"📎 *{nick}* has {count} photo{'s' if count != 1 else ''} attached.")

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nicks = await active_nicknames()
    if not nicks:
        await reply(update, "No listings saved yet. Use `/add` first."); return
    await reply(update, "Which listing do you want to edit?",
                kb.listing_picker(nicks, "edit_listing"))

async def cmd_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    csv_bytes = generate_template_csv()
    await update.effective_message.reply_document(
        document=io.BytesIO(csv_bytes),
        filename="homebot_import_template.csv",
        caption=(
            "📋 *Import template*\n\n"
            "1. Open in Google Sheets or Excel\n"
            "2. Fill in your listings (row 1 is an example — replace it)\n"
            "3. Save as CSV and upload it back here\n\n"
            "Valid ratings: `STRONG` / `OKAY` / `KIV` / `NOGO`\n"
            "Multiple notes: separate with `|` in the notes column"
        ),
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data["awaiting_import"] = True

# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nicks = await active_nicknames()
    if not nicks:
        await reply(update, "No listings saved yet. Use `/add` first."); return
    photo = update.message.photo[-1]
    context.user_data["pending_photo_file_id"] = photo.file_id
    await reply(update, "📎 Got a photo. Which listing is this for?",
                kb.listing_picker(nicks, "photo_listing"))

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_import"):
        return
    doc = update.message.document
    if not doc.file_name.endswith(".csv"):
        await reply(update, "Please upload a `.csv` file."); return
    await reply(update, "📂 Reading your CSV...")
    file    = await doc.get_file()
    raw     = await file.download_as_bytearray()
    rows, errors = parse_import_csv(bytes(raw))
    if errors:
        err_text = "\n".join(f"⚠️ {e}" for e in errors[:5])
        await reply(update, f"*Validation issues:*\n{err_text}")
    if not rows:
        await reply(update, "No valid rows found. Check your CSV and try again.")
        context.user_data["awaiting_import"] = False
        return
    context.user_data["import_rows"]    = rows
    context.user_data["import_index"]   = 0
    context.user_data["awaiting_import"] = False
    await reply(update,
        f"Found *{len(rows)} listing{'s' if len(rows) != 1 else ''}*. How would you like to import them?",
        kb.import_bulk_picker(len(rows))
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    text  = update.message.text.strip()

    if state == AWAIT_NICKNAME:
        nick    = text
        pending = context.user_data.get("pending_listing", {})
        if await db.listing_exists(nick):
            context.user_data["duplicate_nick"] = nick
            await reply(update, f"⚠️ *'{nick}'* already exists. What would you like to do?",
                        kb.duplicate_picker(nick))
            return
        pending["nickname"] = nick
        await db.save_listing(pending)
        context.user_data.pop("state", None)
        context.user_data.pop("pending_listing", None)
        await reply(update,
            f"✓ *{nick}* saved!\n\n"
            "Quick actions:\n• `/note` — add a note\n• `/rate` — set a rating\n• `/status` — set next action"
        )
        return

    if state == AWAIT_STATUS_DESC:
        context.user_data["status_desc"] = text
        context.user_data["state"]       = AWAIT_STATUS_DATE
        await reply(update, "Due date? Type it (e.g. *Wed 9 Apr* or *ASAP*) or type *none* to skip.")
        return

    if state == AWAIT_STATUS_DATE:
        due   = None if text.lower() == "none" else text
        nick  = context.user_data.get("status_nick")
        owner = context.user_data.get("status_owner")
        desc  = context.user_data.get("status_desc")
        action_id = await db.set_next_action(nick, owner, desc, due)
        context.user_data.pop("state", None)
        # Always cancel a previous ASAP job for this listing
        reminders.cancel_asap_reminders(nick)
        # Start 3-hourly check-ins if due date is ASAP
        if due and due.strip().upper() == "ASAP" and action_id:
            reminders.schedule_asap_reminders(context.bot, nick, action_id, owner, desc)
            asap_note = "\n\n⏰ I'll check in every 3 hours until this is updated."
        else:
            asap_note = ""
        due_str = f"  ·  due *{due}*" if due else ""
        await reply(update, f"✓ Next action set for *{nick}*:\n→ *{owner}*: {desc}{due_str}{asap_note}")
        return

    if state == AWAIT_PHOTO_NOTE:
        nick    = context.user_data.get("photo_note_nick")
        file_id = context.user_data.get("pending_photo_file_id")
        sender  = sender_name(update)
        await db.add_note(nick, text, sender, has_photo=True, photo_file_id=file_id)
        context.user_data.pop("state", None)
        await reply(update, f"📝 Note + photo saved to *{nick}*:\n_{text}_")
        return

    if state == AWAIT_IMPORT_RENAME:
        idx  = context.user_data.get("import_rename_index", 0)
        rows = context.user_data.get("import_rows", [])
        if idx < len(rows):
            rows[idx]["nickname"] = text
        context.user_data["state"] = None
        await _show_import_row(update, context, idx)
        return

    if state == AWAIT_EDIT_VALUE:
        nick  = context.user_data.get("edit_nick")
        field = context.user_data.get("edit_field")
        label = context.user_data.get("edit_label", field)
        value = text
        if field in ("rent_sgd", "size_sqft"):
            try:
                value = int(float(text.replace(",", "").replace("$", "").strip()))
            except ValueError:
                await reply(update, f"⚠️ Please enter a number for *{label}* (e.g. `3200`)."); return
        await db.update_listing_field(nick, field, value)
        context.user_data.pop("state", None)
        await reply(update, f"✓ *{nick}* updated:\n*{label}* → {text}")
        return

    if text.startswith("http"):
        await reply(update,
            "To add a listing use:\n`/add [url]`\n"
            "Example: `/add https://www.propertyguru.com.sg/listing/...`")

# ── Callback handler ──────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data.startswith("view_listing:"):
        nick    = data.split(":", 1)[1]
        listing = await db.get_listing(nick)
        if not listing:
            await query.message.reply_text("Listing not found."); return
        na = await db.get_next_action(nick)
        if na:
            listing["na_owner"] = na["owner"]
            listing["na_desc"]  = na["description"]
            listing["na_due"]   = na["due_date"]
        await query.message.reply_text(
            fmt.format_quick_card(listing),
            reply_markup=kb.full_details_button(nick),
            parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("full_view:"):
        nick        = data.split(":", 1)[1]
        listing     = await db.get_listing(nick)
        if not listing:
            await query.message.reply_text("Listing not found."); return
        notes       = await db.get_notes(nick)
        media_count = await db.get_media_count(nick)
        na          = await db.get_next_action(nick)
        if na:
            listing["na_owner"] = na["owner"]
            listing["na_desc"]  = na["description"]
            listing["na_due"]   = na["due_date"]
        await edit_or_reply(update,
            fmt.format_summary_card(listing, notes, media_count))
        return

    if data.startswith("edit_listing:"):
        nick = data.split(":", 1)[1]
        await query.edit_message_text(
            f"Which field do you want to edit for *{nick}*?",
            reply_markup=kb.field_picker(nick), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("edit_field:"):
        parts       = data.split(":", 2)
        nick, field = parts[1], parts[2]
        label       = next((l for l, f in kb.EDIT_FIELDS if f == field), field)
        context.user_data["edit_nick"]  = nick
        context.user_data["edit_field"] = field
        context.user_data["edit_label"] = label
        context.user_data["state"]      = AWAIT_EDIT_VALUE
        hint = " *(numbers only)*" if field in ("rent_sgd", "size_sqft") else ""
        await edit_or_reply(update, f"Enter the new value for *{label}*{hint}:")
        return

    if data.startswith("note_listing:"):
        nick   = data.split(":", 1)[1]
        text   = context.user_data.pop("pending_note", "")
        sender = sender_name(update)
        await db.add_note(nick, text, sender)
        await edit_or_reply(update, f"📝 Note added to *{nick}* by {sender}:\n_{text}_")
        return

    if data.startswith("rate_listing:"):
        nick = data.split(":", 1)[1]
        await query.edit_message_text(
            f"How are you rating *{nick}*?",
            reply_markup=kb.rating_picker(nick), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("set_rating:"):
        _, nick, rating = data.split(":", 2)
        await db.update_listing_rating(nick, rating)
        await edit_or_reply(update, f"✓ *{nick}* rated: {fmt.RATING_LABEL[rating]}")
        return

    if data.startswith("status_listing:"):
        nick = data.split(":", 1)[1]
        await query.edit_message_text(
            f"Who owns the next action for *{nick}*?",
            reply_markup=kb.owner_picker(nick), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("set_status_owner:"):
        _, nick, owner = data.split(":", 2)
        context.user_data["status_nick"]  = nick
        context.user_data["status_owner"] = owner
        context.user_data["state"]        = AWAIT_STATUS_DESC
        await edit_or_reply(update,
            f"What's the action for *{nick}*?\nType it — e.g. *View the unit* or *Send floor plan*")
        return

    if data.startswith("photo_listing:"):
        nick    = data.split(":", 1)[1]
        file_id = context.user_data.get("pending_photo_file_id")
        if file_id:
            await db.add_media(nick, file_id)
        await query.edit_message_text(
            f"📎 Photo attached to *{nick}*.\nWant to add a note with it?",
            reply_markup=kb.photo_note_prompt(nick), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("photo_note_yes:"):
        nick = data.split(":", 1)[1]
        context.user_data["photo_note_nick"] = nick
        context.user_data["state"]           = AWAIT_PHOTO_NOTE
        await edit_or_reply(update, "Type your note:")
        return

    if data.startswith("photo_note_no:"):
        nick = data.split(":", 1)[1]
        await edit_or_reply(update, f"✓ Photo saved to *{nick}*.")
        return

    if data.startswith("archive_listing:"):
        nick = data.split(":", 1)[1]
        await query.edit_message_text(
            f"Archive *{nick}*? It will be hidden but recoverable via `/archived`.",
            reply_markup=kb.archive_confirm(nick), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("archive_confirm:"):
        nick = data.split(":", 1)[1]
        await db.archive_listing(nick)
        await edit_or_reply(update,
            f"🗂 *{nick}* archived. Use `/archived` to see it or `/restore {nick}` to bring it back.")
        return

    if data.startswith("restore_listing:"):
        nick = data.split(":", 1)[1]
        await db.restore_listing(nick)
        await edit_or_reply(update, f"✓ *{nick}* restored!")
        return

    if data.startswith("dup_rename:"):
        context.user_data["state"] = AWAIT_NICKNAME
        await edit_or_reply(update, "What would you like to name this new listing instead?")
        return

    if data.startswith("dup_reassign:"):
        nick    = data.split(":", 1)[1]
        pending = context.user_data.get("pending_listing", {})
        pending["nickname"] = nick
        await db.reassign_listing(nick, pending)
        context.user_data.pop("state", None)
        await edit_or_reply(update,
            f"✓ *{nick}* reassigned to the new URL. All notes and ratings preserved.")
        return

    if data == "import_save_all":
        rows   = context.user_data.get("import_rows", [])
        saved, skipped = 0, 0
        for row in rows:
            if await db.listing_exists(row["nickname"]):
                skipped += 1; continue
            await db.save_listing(row)
            if row.get("rating") and row["rating"] != "UNRATED":
                await db.update_listing_rating(row["nickname"], row["rating"])
            if row.get("next_action_owner") and row.get("next_action_desc"):
                await db.set_next_action(row["nickname"], row["next_action_owner"],
                                         row["next_action_desc"], row.get("next_action_due"))
            for note_text in row.get("notes", []):
                await db.add_note(row["nickname"], note_text, "Import")
            saved += 1
        context.user_data.pop("import_rows", None)
        skip_msg = f"  ·  {skipped} skipped (nickname already exists)" if skipped else ""
        await edit_or_reply(update,
            f"✓ Import complete! *{saved} listing{'s' if saved != 1 else ''}* saved{skip_msg}.\n\n"
            "Use `/details` to see your shortlist.")
        return

    if data == "import_one_by_one":
        context.user_data["import_index"] = 0
        await _show_import_row(update, context, 0)
        return

    if data.startswith("import_save:"):
        idx  = int(data.split(":")[1])
        rows = context.user_data.get("import_rows", [])
        if idx < len(rows):
            row = rows[idx]
            if not await db.listing_exists(row["nickname"]):
                await db.save_listing(row)
                if row.get("rating") and row["rating"] != "UNRATED":
                    await db.update_listing_rating(row["nickname"], row["rating"])
                if row.get("next_action_owner") and row.get("next_action_desc"):
                    await db.set_next_action(row["nickname"], row["next_action_owner"],
                                             row["next_action_desc"], row.get("next_action_due"))
                for note_text in row.get("notes", []):
                    await db.add_note(row["nickname"], note_text, "Import")
        await _next_import_row(update, context, idx)
        return

    if data.startswith("import_skip:"):
        idx = int(data.split(":")[1])
        await _next_import_row(update, context, idx)
        return

    if data.startswith("import_rename:"):
        idx = int(data.split(":")[1])
        context.user_data["import_rename_index"] = idx
        context.user_data["state"]               = AWAIT_IMPORT_RENAME
        await edit_or_reply(update, "What nickname do you want to use for this listing?")
        return

    if data == "cancel":
        await edit_or_reply(update, "Cancelled.")
        return

# ── Import helpers ─────────────────────────────────────────────────────────────

async def _show_import_row(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int):
    rows  = context.user_data.get("import_rows", [])
    total = len(rows)
    if idx >= total:
        await edit_or_reply(update, "✓ Import complete! Use `/details` to see your shortlist.")
        context.user_data.pop("import_rows", None)
        return
    row     = rows[idx]
    preview = fmt.format_import_preview(row, idx + 1, total)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            preview, reply_markup=kb.import_row_picker(idx, row["nickname"]),
            parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(
            preview, reply_markup=kb.import_row_picker(idx, row["nickname"]),
            parse_mode=ParseMode.MARKDOWN)

async def _next_import_row(update: Update, context: ContextTypes.DEFAULT_TYPE, current_idx: int):
    await _show_import_row(update, context, current_idx + 1)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("add",      cmd_add))
    app.add_handler(CommandHandler("details",  cmd_details))
    app.add_handler(CommandHandler("note",     cmd_note))
    app.add_handler(CommandHandler("rate",     cmd_rate))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("archive",  cmd_archive))
    app.add_handler(CommandHandler("archived", cmd_archived))
    app.add_handler(CommandHandler("restore",  cmd_restore))
    app.add_handler(CommandHandler("media",    cmd_media))
    app.add_handler(CommandHandler("edit",     cmd_edit))
    app.add_handler(CommandHandler("import",   cmd_import))
    app.add_handler(MessageHandler(filters.PHOTO,            handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL,     handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    async def on_startup(app):
        await db.init_db()
        reminders.scheduler.start()
        await reminders.reschedule_all(app.bot)
        logger.info("HomeBot started")

    app.post_init = on_startup

    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 8443)),
            webhook_url=WEBHOOK_URL,
        )
    else:
        logger.info("No WEBHOOK_URL set — running in polling mode")
        app.run_polling()

if __name__ == "__main__":
    main()
