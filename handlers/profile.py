from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from keyboards.keyboards import (
    profile_confirm_keyboard,
    profile_credit_type_keyboard,
    profile_edit_menu_keyboard,
    profile_view_keyboard,
    start_keyboard,
)
from models.models import BADGES, CreditType, User
from services.database import AsyncSessionLocal
from services.user_service import create_user, get_user, update_user

router = Router()


class ProfileForm(StatesGroup):
    display_name = State()
    credit_type = State()
    credit_value = State()
    bio = State()
    confirm = State()


def _credit_display_from_data(data: dict) -> str:
    credit_type = data.get("credit_type")
    credit_value = data.get("credit_value")
    display_name = data.get("display_name", "Unknown")

    if credit_type == CreditType.anonymous:
        return "Anonymous"
    if credit_value:
        return f"@{credit_value.lstrip('@')}"
    return display_name


def _profile_text(user: User) -> str:
    badges_list = [badge for badge in (user.badges or "").split(",") if badge]
    badge_display = " ".join(BADGES[badge][0] for badge in badges_list if badge in BADGES)

    text = (
        f"📷 {user.display_name}\n"
        f"Credit: {user.get_credit_display()}\n"
        f"Level: {user.level.value}\n"
        f"Reputation: {user.reputation_points} pts\n"
    )
    if badge_display:
        text += f"Badges: {badge_display}\n"
    if user.bio:
        text += f"\n{user.bio}"

    return text


def _edit_menu_text(user: User) -> str:
    bio = user.bio or "No bio yet."
    return (
        "What would you like to update?\n\n"
        f"Name: {user.display_name}\n"
        f"Credit: {user.get_credit_display()}\n"
        f"Bio: {bio}"
    )


@router.callback_query(F.data == "create_profile")
async def start_profile(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if user:
        await state.clear()
        await callback.message.edit_text(
            "You already have a profile.\n\n"
            f"{_profile_text(user)}",
            reply_markup=profile_view_keyboard(),
        )
    else:
        await callback.message.edit_text(
            "Let's set up your profile.\n\n"
            "First question:\n"
            "What name should appear when your photos are published?\n\n"
            "This can be your real name, artist name, or photography name.",
        )
        await state.set_state(ProfileForm.display_name)

    await callback.answer()


@router.message(ProfileForm.display_name)
async def receive_display_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Send the name as a text message.")
        return

    if len(name) < 2 or len(name) > 64:
        await message.answer("Please choose a name between 2 and 64 characters.")
        return

    data = await state.get_data()
    if data.get("edit_field") == "display_name":
        async with AsyncSessionLocal() as session:
            user = await get_user(session, message.from_user.id)
            if not user:
                await state.clear()
                await message.answer(
                    "You don't have a profile yet.",
                    reply_markup=start_keyboard(has_profile=False),
                )
                return

            user = await update_user(session, user, display_name=name)

        await state.clear()
        await message.answer(
            "Your name has been updated.\n\n"
            f"{_profile_text(user)}",
            reply_markup=profile_view_keyboard(),
        )
        return

    await state.update_data(display_name=name)
    await message.answer(
        f"Nice to meet you, {name}.\n\n"
        "Next question:\n"
        "How should the archive credit your work when a post goes live?",
        reply_markup=profile_credit_type_keyboard(),
    )
    await state.set_state(ProfileForm.credit_type)


@router.callback_query(ProfileForm.credit_type, F.data.startswith("credit_"))
async def receive_credit_type(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    credit_map = {
        "credit_username": CreditType.username,
        "credit_channel": CreditType.channel,
        "credit_anonymous": CreditType.anonymous,
    }
    credit_type = credit_map[callback.data]
    await state.update_data(credit_type=credit_type)

    if data.get("edit_field") == "credit" and credit_type == CreditType.anonymous:
        async with AsyncSessionLocal() as session:
            user = await get_user(session, callback.from_user.id)
            if not user:
                await state.clear()
                await callback.message.edit_text(
                    "You don't have a profile yet.",
                    reply_markup=start_keyboard(has_profile=False),
                )
                await callback.answer()
                return

            user = await update_user(
                session,
                user,
                credit_type=credit_type,
                credit_value=None,
            )

        await state.clear()
        await callback.message.edit_text(
            "Your credit settings have been updated.\n\n"
            f"{_profile_text(user)}",
            reply_markup=profile_view_keyboard(),
        )
        await callback.answer()
        return

    if credit_type == CreditType.anonymous:
        await state.update_data(credit_value=None)
        await callback.message.edit_text(
            "Understood. Your work will be credited as Anonymous.\n\n"
            "Final question:\n"
            "Want to add a short bio? Send it now, or type 'skip'.",
        )
        await state.set_state(ProfileForm.bio)
    else:
        label = "Telegram username" if credit_type == CreditType.username else "channel handle"
        await callback.message.edit_text(
            (
                f"Enter your {label} without the @ symbol:"
                if data.get("edit_field") != "credit"
                else f"Enter your new {label} without the @ symbol:"
            )
        )
        await state.set_state(ProfileForm.credit_value)

    await callback.answer()


@router.message(ProfileForm.credit_value)
async def receive_credit_value(message: Message, state: FSMContext):
    value = (message.text or "").strip().lstrip("@")
    if not value:
        await message.answer("Please enter a valid username or channel handle as text.")
        return

    data = await state.get_data()
    if data.get("edit_field") == "credit":
        async with AsyncSessionLocal() as session:
            user = await get_user(session, message.from_user.id)
            if not user:
                await state.clear()
                await message.answer(
                    "You don't have a profile yet.",
                    reply_markup=start_keyboard(has_profile=False),
                )
                return

            user = await update_user(
                session,
                user,
                credit_type=data["credit_type"],
                credit_value=value,
            )

        await state.clear()
        await message.answer(
            "Your credit settings have been updated.\n\n"
            f"{_profile_text(user)}",
            reply_markup=profile_view_keyboard(),
        )
        return

    await state.update_data(credit_value=value)
    await message.answer(
        "Final question:\n\n"
        "Add a short bio if you want.\n"
        "You can mention your photography style, city, or perspective.\n"
        "Type 'skip' to continue.",
    )
    await state.set_state(ProfileForm.bio)


@router.message(ProfileForm.bio)
async def receive_bio(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    if not text:
        prompt = "Send your bio as text, or type 'skip'."
        if data.get("edit_field") == "bio":
            prompt = "Send your bio as text, or type 'remove' to clear it."
        await message.answer(prompt)
        return

    if data.get("edit_field") == "bio":
        normalized = text.lower()
        bio = None if normalized in {"remove", "clear", "delete"} else text[:256]

        async with AsyncSessionLocal() as session:
            user = await get_user(session, message.from_user.id)
            if not user:
                await state.clear()
                await message.answer(
                    "You don't have a profile yet.",
                    reply_markup=start_keyboard(has_profile=False),
                )
                return

            user = await update_user(session, user, bio=bio)

        await state.clear()
        await message.answer(
            "Your bio has been updated.\n\n"
            f"{_profile_text(user)}",
            reply_markup=profile_view_keyboard(),
        )
        return

    bio = None if text.lower() == "skip" else text[:256]
    await state.update_data(bio=bio)

    summary = (
        "Here's your profile:\n\n"
        f"Name: {data['display_name']}\n"
        f"Credit: {_credit_display_from_data(data)}\n"
    )
    if bio:
        summary += f"Bio: {bio}\n"

    await message.answer(summary, reply_markup=profile_confirm_keyboard())
    await state.set_state(ProfileForm.confirm)


@router.callback_query(ProfileForm.confirm, F.data == "profile_confirm")
async def confirm_profile(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        existing = await get_user(session, callback.from_user.id)
        if existing:
            await update_user(
                session,
                existing,
                display_name=data["display_name"],
                credit_type=data["credit_type"],
                credit_value=data.get("credit_value"),
                bio=data.get("bio"),
            )
        else:
            await create_user(
                session,
                telegram_id=callback.from_user.id,
                display_name=data["display_name"],
                credit_type=data["credit_type"],
                credit_value=data.get("credit_value"),
                bio=data.get("bio"),
            )

    await state.clear()
    await callback.message.edit_text(
        f"Your profile is ready, {data['display_name']}.\n\n"
        "You can now submit your first moment. ✦",
        reply_markup=start_keyboard(has_profile=True),
    )
    await callback.answer()


@router.callback_query(ProfileForm.confirm, F.data == "profile_edit")
async def edit_profile(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Let's start over. What name should appear with your photos?"
    )
    await state.set_state(ProfileForm.display_name)
    await callback.answer()


@router.callback_query(F.data == "edit_profile_menu")
async def show_edit_menu(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    await state.clear()
    if not user:
        await callback.message.edit_text(
            "You don't have a profile yet.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _edit_menu_text(user),
        reply_markup=profile_edit_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "edit_name")
async def prompt_edit_name(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if not user:
        await state.clear()
        await callback.message.edit_text(
            "You don't have a profile yet.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(edit_field="display_name")
    await callback.message.edit_text(
        "Send your new display name.\n\n"
        f"Current: {user.display_name}"
    )
    await state.set_state(ProfileForm.display_name)
    await callback.answer()


@router.callback_query(F.data == "edit_credit")
async def prompt_edit_credit(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if not user:
        await state.clear()
        await callback.message.edit_text(
            "You don't have a profile yet.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(edit_field="credit")
    await callback.message.edit_text(
        "How should the archive credit your work from now on?",
        reply_markup=profile_credit_type_keyboard(),
    )
    await state.set_state(ProfileForm.credit_type)
    await callback.answer()


@router.callback_query(F.data == "edit_bio")
async def prompt_edit_bio(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if not user:
        await state.clear()
        await callback.message.edit_text(
            "You don't have a profile yet.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(edit_field="bio")
    current_bio = user.bio or "No bio yet."
    await callback.message.edit_text(
        "Send your new bio.\n"
        "Type 'remove' to clear it.\n\n"
        f"Current: {current_bio}"
    )
    await state.set_state(ProfileForm.bio)
    await callback.answer()


@router.callback_query(F.data == "my_profile")
async def view_profile(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    await state.clear()
    if not user:
        await callback.message.edit_text(
            "You don't have a profile yet.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _profile_text(user),
        reply_markup=profile_view_keyboard(),
    )
    await callback.answer()
