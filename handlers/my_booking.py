from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
from datetime import datetime

my_bookings_router = Router()
DB_PATH = "database/scheduler.db"

@my_bookings_router.message(F.text == "Мои записи")
async def show_my_bookings(message: Message):
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        today = datetime.now().strftime("%m/%d/%Y")

        async with db.execute("""
            SELECT id, branch, date, time 
            FROM bookings
            WHERE user_id = ? AND date >= ?
            ORDER BY date, time
        """, (user_id, today)) as cursor:
            bookings = await cursor.fetchall()

    if not bookings:
        await message.answer("У вас пока нет активных записей 🙃")
        return

    for booking_id, branch, date, time in bookings:
        try:
            display_date = datetime.strptime(date, "%m/%d/%Y").strftime("%d-%m-%Y")
        except ValueError:
            display_date = date

        text = f"🏢 Магазин: {branch}\n📅 Дата: {display_date}\n⏰ Время: {time}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{booking_id}")]
            ]
        )

        await message.answer(text, reply_markup=keyboard)