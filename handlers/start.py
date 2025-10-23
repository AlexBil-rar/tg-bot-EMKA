from aiogram import Router, F
from aiogram.types import Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

start_router = Router()

@start_router.message(F.text == "/start")
async def start_cmd(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать запись")],
            [KeyboardButton(text="Мои записи")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\nВыберите действие ниже:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )