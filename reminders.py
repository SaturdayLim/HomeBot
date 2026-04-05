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
