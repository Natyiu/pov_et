from aiogram import Bot, F, Router
from aiogram.filters import Command, Filter
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
from services.user_service import (
    add_reputation,
    ban_user,
    get_user,
    list_admin_users,
    list_banned_users,
    list_users_with_submission_counts,
    set_user_admin,
    unban_user,
)

from keyboards.keyboards import (
    admin_back_to_panel_keyboard,
    admin_cancel_keyboard,
    admin_manage_admins_keyboard,
    admin_manage_bans_keyboard,
    admin_panel_keyboard,
    admin_review_keyboard,
)

router = Router()


def _super_admin_id() -> int:
    return settings.ADMIN_USER_ID or settings.ADMIN_CHAT_ID


class IsAdmin(Filter):
    async def __call__(self, event: CallbackQuery | Message) -> bool:
        if not event.from_user:
            return False
        if event.from_user.id == _super_admin_id():
            return True
        async with AsyncSessionLocal() as session:
            user = await get_user(session, event.from_user.id)
        return bool(user and user.is_admin)


class IsSuperAdmin(Filter):
    async def __call__(self, event: CallbackQuery | Message) -> bool:
        return bool(event.from_user and event.from_user.id == _super_admin_id())


class AdminEditForm(StatesGroup):
    waiting_caption = State()


class AdminPanelForm(StatesGroup):
    waiting_user_id = State()


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


@router.callback_query(IsSuperAdmin(), F.data.startswith("admin_edit_"))
async def admin_edit_start(callback: CallbackQuery, state: FSMContext):
    submission_id = int(callback.data.split("_")[-1])
    await state.update_data(editing_submission_id=submission_id)
    await callback.message.answer("Send the new caption:")
    await state.set_state(AdminEditForm.waiting_caption)
    await callback.answer()


@router.message(AdminEditForm.waiting_caption)
async def admin_edit_caption(message: Message, state: FSMContext):
    if not await IsSuperAdmin().__call__(message):
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


@router.callback_query(IsSuperAdmin(), F.data.startswith("admin_feature_"))
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


@router.callback_query(IsSuperAdmin(), F.data.startswith("admin_ban_"))
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


def _parse_telegram_id(text: str) -> int | None:
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    try:
        return int(parts[1].strip().lstrip("@"))
    except ValueError:
        return None


@router.message(IsSuperAdmin(), Command("addadmin"))
async def cmd_add_admin(message: Message, bot: Bot):
    target_id = _parse_telegram_id(message.text or "")
    if target_id is None:
        await message.answer("Usage: /addadmin <telegram_id>")
        return

    async with AsyncSessionLocal() as session:
        user = await get_user(session, target_id)
        if not user:
            await message.answer(
                f"No user with telegram id {target_id} found. "
                "They need to /start the bot and create a profile first."
            )
            return
        await set_user_admin(session, user, True)

    await message.answer(f"Promoted {user.display_name} (id {target_id}) to admin. ✓")
    try:
        await bot.send_message(
            chat_id=target_id,
            text="You've been promoted to admin. You can now approve, reject, and review submissions.",
        )
    except Exception:
        pass


@router.message(IsSuperAdmin(), Command("removeadmin"))
async def cmd_remove_admin(message: Message, bot: Bot):
    target_id = _parse_telegram_id(message.text or "")
    if target_id is None:
        await message.answer("Usage: /removeadmin <telegram_id>")
        return

    if target_id == _super_admin_id():
        await message.answer("Cannot demote the super admin.")
        return

    async with AsyncSessionLocal() as session:
        user = await get_user(session, target_id)
        if not user:
            await message.answer(f"No user with telegram id {target_id} found.")
            return
        if not user.is_admin:
            await message.answer(f"{user.display_name} is not an admin.")
            return
        await set_user_admin(session, user, False)

    await message.answer(f"Removed admin from {user.display_name} (id {target_id}). ✓")
    try:
        await bot.send_message(
            chat_id=target_id,
            text="Your admin access has been removed.",
        )
    except Exception:
        pass


@router.message(IsSuperAdmin(), Command("admins"))
async def cmd_list_admins(message: Message):
    async with AsyncSessionLocal() as session:
        admins = await list_admin_users(session)

    lines = [f"Super admin: id {_super_admin_id()}"]
    if admins:
        lines.append("\nAdmins:")
        for u in admins:
            lines.append(f"• {u.display_name} (id {u.telegram_id})")
    else:
        lines.append("\nNo additional admins.")
    await message.answer("\n".join(lines))


@router.message(IsSuperAdmin(), Command("unban"))
async def cmd_unban(message: Message, bot: Bot):
    target_id = _parse_telegram_id(message.text or "")
    if target_id is None:
        await message.answer("Usage: /unban <telegram_id>")
        return

    async with AsyncSessionLocal() as session:
        user = await get_user(session, target_id)
        if not user:
            await message.answer(f"No user with telegram id {target_id} found.")
            return
        if not user.is_banned:
            await message.answer(f"{user.display_name} is not banned.")
            return
        await unban_user(session, user)

    await message.answer(f"Unbanned {user.display_name} (id {target_id}). ✓")
    try:
        await bot.send_message(
            chat_id=target_id,
            text="Your account has been reinstated. You can submit moments again. ✦",
        )
    except Exception:
        pass


@router.message(IsSuperAdmin(), Command("ban"))
async def cmd_ban(message: Message, bot: Bot):
    target_id = _parse_telegram_id(message.text or "")
    if target_id is None:
        await message.answer("Usage: /ban <telegram_id>")
        return

    async with AsyncSessionLocal() as session:
        user = await get_user(session, target_id)
        if not user:
            await message.answer(f"No user with telegram id {target_id} found.")
            return
        if user.is_banned:
            await message.answer(f"{user.display_name} is already banned.")
            return
        await ban_user(session, user)

    await message.answer(f"Banned {user.display_name} (id {target_id}).")


@router.message(IsSuperAdmin(), Command("banned"))
async def cmd_list_banned(message: Message):
    async with AsyncSessionLocal() as session:
        banned = await list_banned_users(session)

    if not banned:
        await message.answer("No banned users.")
        return

    lines = ["Banned users:"]
    for u in banned:
        lines.append(f"• {u.display_name} (id {u.telegram_id})")
    await message.answer("\n".join(lines))


_PANEL_TITLE = "🛠 Admin Panel\n\nWhat would you like to do?"


async def _show_panel(message: Message, edit: bool = True):
    if edit:
        try:
            await message.edit_text(_PANEL_TITLE, reply_markup=admin_panel_keyboard())
            return
        except TelegramBadRequest:
            pass
    await message.answer(_PANEL_TITLE, reply_markup=admin_panel_keyboard())


@router.message(IsSuperAdmin(), Command("admin"))
async def cmd_admin_panel(message: Message, state: FSMContext):
    await state.clear()
    await _show_panel(message, edit=False)


@router.callback_query(IsSuperAdmin(), F.data == "admin_panel_root")
async def cb_panel_root(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_panel(callback.message, edit=True)
    await callback.answer()


@router.callback_query(IsSuperAdmin(), F.data == "admin_panel_close")
async def cb_panel_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Panel closed.")
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(IsSuperAdmin(), F.data == "admin_panel_admins")
async def cb_panel_admins(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "👥 Admin management",
        reply_markup=admin_manage_admins_keyboard(),
    )
    await callback.answer()


@router.callback_query(IsSuperAdmin(), F.data == "admin_panel_bans")
async def cb_panel_bans(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🚫 Ban management",
        reply_markup=admin_manage_bans_keyboard(),
    )
    await callback.answer()


@router.callback_query(IsSuperAdmin(), F.data == "admin_panel_users")
async def cb_panel_users(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        rows = await list_users_with_submission_counts(session, limit=50)

    if not rows:
        text = "No users yet."
    else:
        lines = ["📋 Users (top 50 by submissions):\n"]
        for user, count in rows:
            flag = ""
            if user.is_admin:
                flag += " 👑"
            if user.is_banned:
                flag += " 🚫"
            lines.append(
                f"• {user.display_name} (id {user.telegram_id}){flag} — {count} submission(s)"
            )
        text = "\n".join(lines)

    if len(text) > 3800:
        text = text[:3800] + "\n…(truncated)"

    await callback.message.edit_text(text, reply_markup=admin_back_to_panel_keyboard())
    await callback.answer()


@router.callback_query(IsSuperAdmin(), F.data == "admin_panel_pending")
async def cb_panel_pending(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from services.submission_service import get_pending_submissions

    async with AsyncSessionLocal() as session:
        pending = await get_pending_submissions(session)

    if not pending:
        text = "📥 No pending submissions."
    else:
        lines = [f"📥 Pending submissions ({len(pending)}):\n"]
        for sub in pending[:50]:
            media_count = len(sub.media)
            location = sub.location or "no location"
            lines.append(
                f"• #{sub.id} — {media_count} photo(s), {location}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=admin_back_to_panel_keyboard())
    await callback.answer()


_ACTION_PROMPTS = {
    "add_admin": "Send the telegram id of the user to promote to admin.\n\n(They must have started the bot first.)",
    "remove_admin": "Send the telegram id of the admin to demote.",
    "ban": "Send the telegram id of the user to ban.",
    "unban": "Send the telegram id of the user to unban.",
}


@router.callback_query(IsSuperAdmin(), F.data.startswith("admin_action_"))
async def cb_admin_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data[len("admin_action_"):]

    if action == "list_admins":
        async with AsyncSessionLocal() as session:
            admins = await list_admin_users(session)
        lines = [f"👑 Super admin: id {_super_admin_id()}"]
        if admins:
            lines.append("\nAdmins:")
            for u in admins:
                lines.append(f"• {u.display_name} (id {u.telegram_id})")
        else:
            lines.append("\nNo additional admins.")
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=admin_back_to_panel_keyboard(),
        )
        await callback.answer()
        return

    if action == "list_banned":
        async with AsyncSessionLocal() as session:
            banned = await list_banned_users(session)
        if not banned:
            text = "✅ No banned users."
        else:
            lines = ["🚫 Banned users:"]
            for u in banned:
                lines.append(f"• {u.display_name} (id {u.telegram_id})")
            text = "\n".join(lines)
        await callback.message.edit_text(text, reply_markup=admin_back_to_panel_keyboard())
        await callback.answer()
        return

    prompt = _ACTION_PROMPTS.get(action)
    if not prompt:
        await callback.answer("Unknown action.", show_alert=True)
        return

    # Super-admin gating for admin promotion/demotion
    if action in ("add_admin", "remove_admin"):
        if callback.from_user.id != _super_admin_id():
            await callback.answer("Only the super admin can manage admins.", show_alert=True)
            return

    await state.set_state(AdminPanelForm.waiting_user_id)
    await state.update_data(panel_action=action)
    await callback.message.edit_text(prompt, reply_markup=admin_cancel_keyboard())
    await callback.answer()


@router.message(AdminPanelForm.waiting_user_id, IsSuperAdmin())
async def handle_panel_user_id(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    action = data.get("panel_action")
    raw = (message.text or "").strip().lstrip("@")
    try:
        target_id = int(raw)
    except ValueError:
        await message.answer(
            "That doesn't look like a telegram id. Send a number, or tap Cancel.",
            reply_markup=admin_cancel_keyboard(),
        )
        return

    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await get_user(session, target_id)

        if not user:
            await message.answer(
                f"No user with telegram id {target_id} found. "
                "They need to /start the bot first.",
                reply_markup=admin_back_to_panel_keyboard(),
            )
            return

        if action == "add_admin":
            if user.is_admin:
                result = f"{user.display_name} is already an admin."
            else:
                await set_user_admin(session, user, True)
                result = f"Promoted {user.display_name} (id {target_id}) to admin. ✓"
                try:
                    await bot.send_message(
                        chat_id=target_id,
                        text="You've been promoted to admin. You can now approve, reject, and review submissions.",
                    )
                except Exception:
                    pass

        elif action == "remove_admin":
            if target_id == _super_admin_id():
                result = "Cannot demote the super admin."
            elif not user.is_admin:
                result = f"{user.display_name} is not an admin."
            else:
                await set_user_admin(session, user, False)
                result = f"Removed admin from {user.display_name} (id {target_id}). ✓"
                try:
                    await bot.send_message(
                        chat_id=target_id,
                        text="Your admin access has been removed.",
                    )
                except Exception:
                    pass

        elif action == "ban":
            if user.is_banned:
                result = f"{user.display_name} is already banned."
            else:
                await ban_user(session, user)
                result = f"Banned {user.display_name} (id {target_id})."

        elif action == "unban":
            if not user.is_banned:
                result = f"{user.display_name} is not banned."
            else:
                await unban_user(session, user)
                result = f"Unbanned {user.display_name} (id {target_id}). ✓"
                try:
                    await bot.send_message(
                        chat_id=target_id,
                        text="Your account has been reinstated. You can submit moments again. ✦",
                    )
                except Exception:
                    pass

        else:
            result = "Unknown action."

    await message.answer(result, reply_markup=admin_back_to_panel_keyboard())
