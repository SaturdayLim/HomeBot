"""
reminders.py — Viewing appointment reminders
"""

import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
import database as db

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def send_reminder(bot: Bot, nickname: str, viewing_dt_str: str, hours_before: int):
    group_id   = await db.get_config("GROUP_CHAT_ID")
    michael_id = os.getenv("MICHAEL_TELEGRAM_ID")
    natalie_id = os.getenv("NATALIE_TELEGRAM_ID")

    msg = (
        f"📅 *Reminder* — viewing {'tomorrow' if hours_before == 24 else 'in 1 hour'}!\n\n"
        f"*{nickname}*\n{viewing_dt_str}"
    )
    targets = [t for t in [group_id, michael_id, natalie_id]
               if t and t != "REPLACE_ME"]
    for chat_id in targets:
        try:
            await bot.send_message(int(chat_id), msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Reminder failed for {chat_id}: {e}")

async def schedule_reminders(bot: Bot, nickname: str, viewing_dt_str: str):
    try:
        viewing_dt = datetime.fromisoformat(viewing_dt_str)
    except ValueError:
        return
    now          = datetime.now()
    reminder_24h = viewing_dt - timedelta(hours=24)
    reminder_1h  = viewing_dt - timedelta(hours=1)
    for jid in [f"r24_{nickname}", f"r1_{nickname}"]:
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)
    if reminder_24h > now:
        scheduler.add_job(send_reminder, "date", run_date=reminder_24h,
                          args=[bot, nickname, viewing_dt_str, 24], id=f"r24_{nickname}")
    if reminder_1h > now:
        scheduler.add_job(send_reminder, "date", run_date=reminder_1h,
                          args=[bot, nickname, viewing_dt_str, 1],  id=f"r1_{nickname}")

async def reschedule_all(bot: Bot):
    listings = await db.get_upcoming_viewings()
    for l in listings:
        if l.get("viewing_dt"):
            await schedule_reminders(bot, l["nickname"], l["viewing_dt"])
    logger.info(f"Rescheduled reminders for {len(listings)} upcoming viewings")

    asap = await db.get_asap_actions()
    for a in asap:
        schedule_asap_reminders(bot, a["nickname"], a["action_id"], a["owner"], a["description"])
    if asap:
        logger.info(f"Rescheduled ASAP reminders for {len(asap)} listings")

# ── ASAP reminders ─────────────────────────────────────────────────────────────

async def _send_asap_reminder(bot: Bot, nickname: str, action_id: int, owner: str, description: str):
    """Fire every 3 h. Auto-cancels if the action has been superseded."""
    current = await db.get_next_action(nickname)
    if not current or current["id"] != action_id:
        cancel_asap_reminders(nickname)
        return
    group_id = await db.get_config("GROUP_CHAT_ID")
    if not group_id or group_id == "REPLACE_ME":
        return
    msg = (
        f"⏰ *ASAP check-in* — still pending!\n\n"
        f"*{nickname}*\n"
        f"→ *{owner}*: {description}\n\n"
        f"Use /status to update or mark as done."
    )
    try:
        await bot.send_message(int(group_id), msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"ASAP reminder failed for {group_id}: {e}")

def schedule_asap_reminders(bot: Bot, nickname: str, action_id: int, owner: str, description: str):
    """Schedule 3-hourly check-ins for an ASAP next action."""
    jid = f"asap_{nickname}"
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    scheduler.add_job(
        _send_asap_reminder,
        "interval",
        hours=3,
        args=[bot, nickname, action_id, owner, description],
        id=jid,
    )
    logger.info(f"Scheduled ASAP check-ins every 3h for '{nickname}'")

def cancel_asap_reminders(nickname: str):
    """Cancel ASAP check-ins for a listing (call whenever a new next action is set)."""
    jid = f"asap_{nickname}"
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
        logger.info(f"Cancelled ASAP reminders for '{nickname}'")
