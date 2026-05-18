from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from keyboards.keyboards import (
    profile_confirm_keyboard,
    profile_credit_type_keyboard,
    start_keyboard,
)
from models.models import BADGES, CreditType
from services.database import AsyncSessionLocal
from services.user_service import create_user, get_user, update_user

router = Router()


class ProfileForm(StatesGroup):
    display_name = State()
    credit_type = State()
    credit_value = State()
    bio = State()
    confirm = State()


@router.callback_query(F.data == "create_profile")
async def start_profile(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if user:
        await state.update_data(
            display_name=user.display_name,
            credit_type=user.credit_type,
            credit_value=user.credit_value,
            bio=user.bio,
            editing=True,
        )
        await callback.message.edit_text(
            f"You already have a profile, {user.display_name}.\n\n"
            f"Level: {user.level.value}\n"
            f"Reputation: {user.reputation_points} pts\n\n"
            "Would you like to update it?",
            reply_markup=profile_confirm_keyboard(),
        )
        await state.set_state(ProfileForm.confirm)
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
    name = message.text.strip()
    if len(name) < 2 or len(name) > 64:
        await message.answer("Please choose a name between 2 and 64 characters.")
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
    credit_map = {
        "credit_username": CreditType.username,
        "credit_channel": CreditType.channel,
        "credit_anonymous": CreditType.anonymous,
    }
    credit_type = credit_map[callback.data]
    await state.update_data(credit_type=credit_type)

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
            f"Enter your {label} without the @ symbol:"
        )
        await state.set_state(ProfileForm.credit_value)

    await callback.answer()


@router.message(ProfileForm.credit_value)
async def receive_credit_value(message: Message, state: FSMContext):
    value = message.text.strip().lstrip("@")
    if not value:
        await message.answer("Please enter a valid username or channel handle.")
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
    bio = None if text.lower() == "skip" else text[:256]
    await state.update_data(bio=bio)

    data = await state.get_data()
    credit_display = "Anonymous"
    if data.get("credit_value"):
        credit_display = f"@{data['credit_value']}"

    summary = (
        "Here's your profile:\n\n"
        f"Name: {data['display_name']}\n"
        f"Credit: {credit_display}\n"
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


@router.callback_query(F.data == "my_profile")
async def view_profile(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    if not user:
        await callback.message.edit_text(
            "You don't have a profile yet.",
            reply_markup=start_keyboard(has_profile=False),
        )
        await callback.answer()
        return

    badges_list = [b for b in (user.badges or "").split(",") if b]
    badge_display = " ".join(BADGES[b][0] for b in badges_list if b in BADGES)

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

    await callback.message.edit_text(text, reply_markup=start_keyboard(has_profile=True))
    await callback.answer()
