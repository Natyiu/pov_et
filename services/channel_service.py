from aiogram import Bot
from aiogram.types import InputMediaPhoto

from config import settings
from models.models import Submission, User


def build_post_caption(submission: Submission, user: User) -> str:
    lines = []

    if submission.location:
        lines.append(f"📍 {submission.location}")

    if submission.caption:
        lines.append(f'\n"{submission.caption}"')

    credit = user.get_credit_display()
    lines.append(f"\n📷 by {credit}")

    if submission.status.value in ("featured_weekly", "featured_monthly"):
        lines.append("\n✨ Featured")

    return "\n".join(lines)


async def publish_submission(
    bot: Bot,
    submission: Submission,
    user: User,
) -> int | None:
    caption = build_post_caption(submission, user)
    media_list = sorted(submission.media, key=lambda m: m.order_index)

    if not media_list:
        return None

    channel = settings.CHANNEL_ID

    if len(media_list) == 1:
        msg = await bot.send_photo(
            chat_id=channel,
            photo=media_list[0].telegram_file_id,
            caption=caption,
        )
        return msg.message_id

    media_group = []
    for idx, m in enumerate(media_list):
        media_group.append(
            InputMediaPhoto(
                media=m.telegram_file_id,
                caption=caption if idx == 0 else None,
            )
        )
    messages = await bot.send_media_group(chat_id=channel, media=media_group)
    return messages[0].message_id if messages else None


async def publish_weekly_feature(
    bot: Bot,
    submissions: list[Submission],
    users: dict[int, User],
    week_label: str = "",
) -> None:
    header = "✨ This Week in Ethiopia"
    if week_label:
        header += f" — {week_label}"
    header += "\nA curated selection of moments across the country.\n"

    await bot.send_message(chat_id=settings.CHANNEL_ID, text=header)

    for submission in submissions:
        user = users.get(submission.user_id)
        if user:
            await publish_submission(bot, submission, user)


async def publish_photographer_spotlight(
    bot: Bot,
    user: User,
    intro_text: str,
    featured_submissions: list[Submission],
) -> None:
    credit = user.get_credit_display()
    header = (
        f"🌟 Photographer Spotlight\n\n"
        f"{user.display_name}\n"
        f"{credit}\n\n"
        f"{intro_text}"
    )
    await bot.send_message(chat_id=settings.CHANNEL_ID, text=header)

    users_map = {user.id: user}
    for submission in featured_submissions:
        await publish_submission(bot, submission, users_map[submission.user_id])
