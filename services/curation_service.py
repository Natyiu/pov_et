"""
Curation service — run weekly/monthly via cron or a scheduler like APScheduler.

Example usage:
  from services.curation_service import run_weekly_feature
  await run_weekly_feature(bot)
"""
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select

from models.models import Submission, SubmissionStatus, User
from services.channel_service import publish_weekly_feature
from services.database import AsyncSessionLocal
from services.user_service import add_reputation


async def get_weekly_feature_candidates(session, limit: int = 15) -> list[Submission]:
    since = datetime.utcnow() - timedelta(days=7)
    result = await session.execute(
        select(Submission)
        .where(
            Submission.status == SubmissionStatus.approved,
            Submission.reviewed_at >= since,
            Submission.admin_note.contains("FEATURE CANDIDATE"),
        )
        .order_by(Submission.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def run_weekly_feature(bot: Bot, week_label: str = ""):
    async with AsyncSessionLocal() as session:
        submissions = await get_weekly_feature_candidates(session)
        if not submissions:
            return

        user_ids = {s.user_id for s in submissions}
        result = await session.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users = {u.id: u for u in result.scalars().all()}

        await publish_weekly_feature(bot, submissions, users, week_label)

        for submission in submissions:
            submission.status = SubmissionStatus.featured_weekly
            user = users.get(submission.user_id)
            if user:
                await add_reputation(session, user, "weekly_featured")
                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text="Your frame was selected for this week's curated collection. ✦",
                    )
                except Exception:
                    pass

        await session.commit()
