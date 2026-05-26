import asyncio

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import settings
from keyboards.keyboards import (
    admin_review_keyboard,
    start_keyboard,
    submission_confirm_keyboard,
    submission_hashtag_keyboard,
    submission_skip_keyboard,
)
from services.database import AsyncSessionLocal
from services.submission_service import create_submission
from services.user_service import get_user

router = Router()

_media_buffer: dict[int, list[str]] = {}
_media_timers: dict[int, asyncio.Task] = {}


class SubmitForm(StatesGroup):
    waiting_photos = State()
    waiting_location = State()
    waiting_caption = State()
    waiting_hashtags = State()
    confirming = State()


def _cancel_media_timer(user_id: int):
    task = _media_timers.pop(user_id, None)
    if task:
        task.cancel()


async def _prompt_location(message: Message, state: FSMContext):
    await message.answer(
        "Where was this taken? (city, region, or landmark)\n\n"
        "Example: Bahir Dar, Lalibela, Merkato Addis Ababa\n\n"
        "Send the location as text, or tap Skip.",
        reply_markup=submission_skip_keyboard("loc_skip"),
    )
    await state.set_state(SubmitForm.waiting_location)


async def _prompt_caption(message: Message, state: FSMContext):
    await message.answer(
        "Write a caption for your photo.\n\n"
        "A short sentence or two — what's the moment? What does it feel like?\n\n"
        "Send the caption as text, or tap Skip.",
        reply_markup=submission_skip_keyboard("cap_skip"),
    )
    await state.set_state(SubmitForm.waiting_caption)


async def _prompt_hashtags(message: Message, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("hashtags") or [])
    await message.answer(
        "Pick any hashtags that fit your photo.\n"
        "Tap to toggle. Tap Done when you're finished, or Skip to add none.",
        reply_markup=submission_hashtag_keyboard(selected),
    )
    await state.set_state(SubmitForm.waiting_hashtags)


async def _show_summary(message: Message, state: FSMContext):
    data = await state.get_data()
    count = len(data.get("file_ids", []))
    lines = [f"Ready to submit {count} photo(s)."]
    if data.get("location"):
        lines.append(f"Location: {data['location']}")
    if data.get("caption"):
        lines.append(f"Caption: {data['caption']}")
    tags = data.get("hashtags") or []
    if tags:
        lines.append("Tags: " + " ".join(f"#{t}" for t in tags))
    await message.answer(
        "\n".join(lines),
        reply_markup=submission_confirm_keyboard(),
    )
    await state.set_state(SubmitForm.confirming)


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
    await state.update_data(file_ids=[], caption=None, location=None, hashtags=[])
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
        await message.answer(f"{count} photo{suffix} received.")
        await _prompt_location(message, state)

    _media_timers[user_id] = asyncio.create_task(finalize())


@router.message(SubmitForm.waiting_location)
async def receive_location(message: Message, state: FSMContext):
    location = (message.text or "").strip()[:128]
    if not location:
        await message.answer(
            "Send the location as text, or tap Skip.",
            reply_markup=submission_skip_keyboard("loc_skip"),
        )
        return
    await state.update_data(location=location)
    await _prompt_caption(message, state)


@router.callback_query(SubmitForm.waiting_location, F.data == "loc_skip")
async def skip_location(callback: CallbackQuery, state: FSMContext):
    await state.update_data(location=None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _prompt_caption(callback.message, state)
    await callback.answer()


@router.message(SubmitForm.waiting_caption)
async def receive_caption(message: Message, state: FSMContext):
    caption = (message.text or "").strip()[:500]
    if not caption:
        await message.answer(
            "Send the caption as text, or tap Skip.",
            reply_markup=submission_skip_keyboard("cap_skip"),
        )
        return
    await state.update_data(caption=caption)
    await _prompt_hashtags(message, state)


@router.callback_query(SubmitForm.waiting_caption, F.data == "cap_skip")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await state.update_data(caption=None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _prompt_hashtags(callback.message, state)
    await callback.answer()


@router.callback_query(SubmitForm.waiting_hashtags, F.data.startswith("tag_"))
async def toggle_hashtag(callback: CallbackQuery, state: FSMContext):
    tag = callback.data[len("tag_"):]
    data = await state.get_data()
    selected = set(data.get("hashtags") or [])
    if tag in selected:
        selected.discard(tag)
    else:
        selected.add(tag)
    await state.update_data(hashtags=list(selected))
    try:
        await callback.message.edit_reply_markup(
            reply_markup=submission_hashtag_keyboard(selected),
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(SubmitForm.waiting_hashtags, F.data == "tags_done")
async def finish_hashtags(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_summary(callback.message, state)
    await callback.answer()


@router.callback_query(SubmitForm.waiting_hashtags, F.data == "tags_skip")
async def skip_hashtags(callback: CallbackQuery, state: FSMContext):
    await state.update_data(hashtags=[])
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_summary(callback.message, state)
    await callback.answer()


@router.callback_query(SubmitForm.confirming, F.data == "submit_confirm")
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
            hashtags=data.get("hashtags") or None,
        )

    await state.clear()
    await callback.message.edit_text(
        "Your moment has been received.\nIt's now under curation. ✦\n\n"
        "You can submit another moment any time.",
        reply_markup=start_keyboard(has_profile=True),
    )

    await notify_admin(bot, submission, user, file_ids, data.get("hashtags") or [])
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


async def notify_admin(
    bot: Bot,
    submission,
    user,
    file_ids: list[str],
    hashtags: list[str],
):
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
    if hashtags:
        info += "Tags: " + " ".join(f"#{t}" for t in hashtags) + "\n"

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
