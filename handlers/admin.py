from aiogram import Bot, F, Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from config import settings
from models.models import SubmissionStatus, User
from services.channel_service import publish_submission
from services.database import AsyncSessionLocal
from services.submission_service import (
    get_submission,
    update_submission_caption,
    update_submission_status,
)
from services.user_service import add_reputation, ban_user

router = Router()


def _admin_user_id() -> int:
    return settings.ADMIN_USER_ID or settings.ADMIN_CHAT_ID


class IsAdmin(Filter):
    async def __call__(self, event: CallbackQuery | Message) -> bool:
        return bool(event.from_user and event.from_user.id == _admin_user_id())


class AdminEditForm(StatesGroup):
    waiting_caption = State()


async def _get_user(session, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _edit_review_message(message, text: str):
    if message.text is not None:
        await message.edit_text(text)
    else:
        await message.edit_caption(text)


async def _append_review_note(message, note: str):
    current = message.text or message.caption or ""
    text = f"{current}\n\n{note}" if current else note
    await _edit_review_message(message, text)


async def _safe_append_review_note(message, note: str):
    try:
        await _append_review_note(message, note)
    except TelegramBadRequest:
        await message.answer(note)


@router.callback_query(IsAdmin(), F.data.startswith("admin_approve_"))
async def admin_approve(callback: CallbackQuery, bot: Bot):
    submission_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        submission = await get_submission(session, submission_id)
        if not submission:
            await callback.answer("Submission not found.", show_alert=True)
            return

        if submission.status != SubmissionStatus.pending:
            await callback.answer("Already reviewed.", show_alert=True)
            return

        user = await _get_user(session, submission.user_id)
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return

        channel_msg_id = await publish_submission(bot, submission, user)
        await update_submission_status(
            session,
            submission,
            status=SubmissionStatus.approved,
            channel_message_id=channel_msg_id,
        )

        new_pts, leveled_up = await add_reputation(session, user, "approved")

    await _safe_append_review_note(
        callback.message,
        "✅ Approved and published.",
    )

    level_msg = f"\nYou've reached: {user.level.value} ✦" if leveled_up else ""
    user_notification_sent = False
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=(
                "Your moment has been added to the archive. ✦\n"
                f"+1 reputation point ({new_pts} total){level_msg}"
            ),
        )
        user_notification_sent = True
    except Exception:
        pass

    if not user_notification_sent:
        await callback.message.answer(
            f"Approved submission #{submission_id}, but I could not message user {user.telegram_id} about the score."
        )

    await callback.answer("Approved ✓")


@router.callback_query(IsAdmin(), F.data.startswith("admin_reject_"))
async def admin_reject(callback: CallbackQuery, bot: Bot):
    submission_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        submission = await get_submission(session, submission_id)
        if not submission or submission.status != SubmissionStatus.pending:
            await callback.answer("Already reviewed.", show_alert=True)
            return

        user = await _get_user(session, submission.user_id)
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return

        await update_submission_status(
            session,
            submission,
            status=SubmissionStatus.rejected,
        )

    await _safe_append_review_note(callback.message, "❌ Not selected for this feed.")

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text="This one wasn't selected for the main feed. Keep shooting. ✦",
        )
    except Exception:
        pass

    await callback.answer("Rejected")


@router.callback_query(IsAdmin(), F.data.startswith("admin_edit_"))
async def admin_edit_start(callback: CallbackQuery, state: FSMContext):
    submission_id = int(callback.data.split("_")[-1])
    await state.update_data(editing_submission_id=submission_id)
    await callback.message.answer("Send the new caption:")
    await state.set_state(AdminEditForm.waiting_caption)
    await callback.answer()


@router.message(AdminEditForm.waiting_caption)
async def admin_edit_caption(message: Message, state: FSMContext):
    if not await IsAdmin().__call__(message):
        return

    data = await state.get_data()
    submission_id = data["editing_submission_id"]

    async with AsyncSessionLocal() as session:
        submission = await get_submission(session, submission_id)
        if not submission:
            await message.answer(f"Submission #{submission_id} not found.")
            await state.clear()
            return
        await update_submission_caption(session, submission, message.text.strip())

    await state.clear()
    await message.answer(f"Caption updated for submission #{submission_id}.")


@router.callback_query(IsAdmin(), F.data.startswith("admin_feature_"))
async def admin_mark_feature(callback: CallbackQuery):
    submission_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        submission = await get_submission(session, submission_id)
        if not submission:
            await callback.answer("Not found.", show_alert=True)
            return
        submission.admin_note = f"{submission.admin_note or ''} [FEATURE CANDIDATE]".strip()
        await session.commit()

    await _safe_append_review_note(callback.message, "📌 Marked as feature candidate.")
    await callback.answer("Marked ✓")


@router.callback_query(IsAdmin(), F.data.startswith("admin_ban_"))
async def admin_ban_user(callback: CallbackQuery, bot: Bot):
    submission_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        submission = await get_submission(session, submission_id)
        if not submission:
            await callback.answer("Not found.", show_alert=True)
            return

        user = await _get_user(session, submission.user_id)
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return

        await ban_user(session, user)

    await _safe_append_review_note(callback.message, f"🚫 User {user.display_name} banned.")
    await callback.answer("User banned")
