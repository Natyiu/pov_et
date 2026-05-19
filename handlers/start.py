from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.keyboards import back_to_start_keyboard, start_keyboard
from services.database import AsyncSessionLocal
from services.user_service import get_user

router = Router()

WELCOME_TEXT = (
    "Welcome to Ethiopia Visual Archive 📷\n\n"
    "Share your moments, stories, and perspectives from anywhere in Ethiopia.\n\n"
    "Selected photos will be featured in our public archive channel — "
    "a living visual memory of Ethiopian life."
)

GUIDELINES_TEXT = (
    "📋 What we're looking for\n\n"
    "• Everyday moments that carry weight\n"
    "• Streets, light, weather, people\n"
    "• Coffee scenes, architecture, travel\n"
    "• Portraits with atmosphere\n"
    "• Documentary and emotional frames\n\n"
    "📋 What we're not\n\n"
    "• A photography contest\n"
    "• A social media likes machine\n"
    "• A place for heavily filtered spam\n\n"
    "This is an archive. Every accepted frame becomes part of something lasting.\n\n"
    "Quality over quantity. One meaningful photo is worth more than ten."
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, message.from_user.id)

    greeting = WELCOME_TEXT
    if user:
        greeting = f"Welcome back, {user.display_name} 📷\n\nWhat would you like to do?"

    await message.answer(greeting, reply_markup=start_keyboard(has_profile=bool(user)))


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    await state.clear()
    await callback.message.edit_text(
        "What would you like to do?",
        reply_markup=start_keyboard(has_profile=bool(user)),
    )
    await callback.answer()


@router.callback_query(F.data == "guidelines")
async def show_guidelines(callback: CallbackQuery):
    await callback.message.edit_text(
        GUIDELINES_TEXT,
        reply_markup=back_to_start_keyboard(),
    )
    await callback.answer()
