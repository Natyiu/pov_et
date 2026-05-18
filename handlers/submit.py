import asyncio

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import settings
from keyboards.keyboards import (
    admin_review_keyboard,
    start_keyboard,
    submission_add_more_keyboard,
    submission_confirm_keyboard,
)
from services.database import AsyncSessionLocal
from services.submission_service import create_submission
from services.user_service import get_user

router = Router()

_media_buffer: dict[int, list[str]] = {}
_media_timers: dict[int, asyncio.Task] = {}


class SubmitForm(StatesGroup):
    waiting_photos = State()
    adding_caption = State()
    adding_location = State()
    confirming = State()


def _cancel_media_timer(user_id: int):
    task = _media_timers.pop(user_id, None)
    if task:
        task.cancel()


@router.callback_query(F.data == "submit_photo")
async def start_submission(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if not user:
        await callback.message.edit_text(
            "You'll need a profile before submitting.\n"
            "Use the button below to create one first.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    if user.is_banned:
        await callback.message.edit_text("Your account is not permitted to submit.")
        await callback.answer()
        return

    await callback.message.edit_text(
        "Send your photo or photos.\n\n"
        "You can send up to 10 images at once as a media group."
    )
    await state.set_state(SubmitForm.waiting_photos)
    await state.update_data(file_ids=[], caption=None, location=None)
    await callback.answer()


@router.message(SubmitForm.waiting_photos, F.photo)
async def receive_photo(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    data = await state.get_data()
    file_ids = data.get("file_ids", [])

    photo = message.photo[-1]
    file_ids.append(photo.file_id)
    await state.update_data(file_ids=file_ids)

    _cancel_media_timer(user_id)

    async def finalize():
        try:
            await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            return

        current_data = await state.get_data()
        count = len(current_data.get("file_ids", []))
        suffix = "s" if count > 1 else ""
        await message.answer(
            f"{count} photo{suffix} received.\n\n"
            "Would you like to add a caption or location before submitting?",
            reply_markup=submission_add_more_keyboard(),
        )

    _media_timers[user_id] = asyncio.create_task(finalize())


@router.callback_query(SubmitForm.waiting_photos, F.data == "add_caption")
async def prompt_caption(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Write a caption for your photo.\n\n"
        "A short sentence or two. What's the moment? What does it feel like?"
    )
    await state.set_state(SubmitForm.adding_caption)
    await callback.answer()


@router.message(SubmitForm.adding_caption)
async def receive_caption(message: Message, state: FSMContext):
    caption = message.text.strip()[:500]
    await state.update_data(caption=caption)
    await message.answer(
        "Caption noted.\n\nAdd a location? - or tap Submit.",
        reply_markup=submission_add_more_keyboard(),
    )
    await state.set_state(SubmitForm.waiting_photos)


@router.callback_query(SubmitForm.waiting_photos, F.data == "add_location")
async def prompt_location(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Where was this taken? (city, region, or landmark)\n\n"
        "Example: Bahir Dar, Lalibela, Merkato Addis Ababa"
    )
    await state.set_state(SubmitForm.adding_location)
    await callback.answer()


@router.message(SubmitForm.adding_location)
async def receive_location(message: Message, state: FSMContext):
    location = message.text.strip()[:128]
    await state.update_data(location=location)
    data = await state.get_data()
    count = len(data.get("file_ids", []))

    summary_lines = [f"Ready to submit {count} photo(s)."]
    if data.get("caption"):
        summary_lines.append("Caption saved.")
    if data.get("location"):
        summary_lines.append(f"Location: {data['location']}")

    await message.answer(
        "\n".join(summary_lines),
        reply_markup=submission_confirm_keyboard(),
    )
    await state.set_state(SubmitForm.waiting_photos)


@router.callback_query(SubmitForm.waiting_photos, F.data == "submit_confirm")
async def confirm_submission(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    file_ids = data.get("file_ids", [])

    if not file_ids:
        await callback.answer("No photos to submit.", show_alert=True)
        return

    _cancel_media_timer(callback.from_user.id)

    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)
        submission = await create_submission(
            session,
            user_id=user.id,
            caption=data.get("caption"),
            location=data.get("location"),
            file_ids=file_ids,
        )

    await state.clear()
    await callback.message.edit_text(
        "Your moment has been received.\nIt's now under curation. ✦\n\n"
        "You can submit another moment any time.",
        reply_markup=start_keyboard(has_profile=True),
    )

    await notify_admin(bot, submission, user, file_ids)
    await callback.answer()


@router.callback_query(F.data == "submit_cancel")
async def cancel_submission(callback: CallbackQuery, state: FSMContext):
    _cancel_media_timer(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "Submission cancelled.",
        reply_markup=start_keyboard(has_profile=True),
    )
    await callback.answer()


async def notify_admin(bot: Bot, submission, user, file_ids: list[str]):
    from aiogram.types import InputMediaPhoto

    admin_chat = settings.ADMIN_USER_ID or settings.ADMIN_CHAT_ID

    credit = user.get_credit_display()
    info = (
        f"📥 New submission #{submission.id}\n"
        f"From: {user.display_name} ({credit})\n"
        f"Level: {user.level.value} | {user.reputation_points} pts\n"
    )
    if submission.location:
        info += f"Location: {submission.location}\n"
    if submission.caption:
        info += f"Caption: {submission.caption}\n"

    if len(file_ids) == 1:
        await bot.send_photo(
            chat_id=admin_chat,
            photo=file_ids[0],
            caption=info,
            reply_markup=admin_review_keyboard(submission.id),
        )
    else:
        media_group = [
            InputMediaPhoto(media=fid, caption=info if idx == 0 else None)
            for idx, fid in enumerate(file_ids)
        ]
        await bot.send_media_group(chat_id=admin_chat, media=media_group)
        await bot.send_message(
            chat_id=admin_chat,
            text=f"⬆️ Submission #{submission.id} above",
            reply_markup=admin_review_keyboard(submission.id),
        )
