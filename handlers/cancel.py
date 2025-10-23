from aiogram import Router, F
from aiogram.types import CallbackQuery
import aiosqlite
from services.email_sender import cancel_email

DB_PATH = "database/scheduler.db"

router = Router()

@router.callback_query(F.data.startswith("cancel_"))
async def cancel_booking(callback: CallbackQuery):
    appointment_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT name, phone, branch, date, time
            FROM bookings
            WHERE id = ?
        """, (appointment_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            await callback.message.edit_text("⚠️ Запись уже удалена или не найдена.")
            await callback.answer()
            return

        name, phone, branch, date, time = row
        data = {
            "name": name,
            "phone": phone,
            "branch": branch,
            "date": date,
            "time": time
        }

        await db.execute("DELETE FROM bookings WHERE id = ?", (appointment_id,))

        await db.execute("""
            DELETE FROM tg_schedule
            WHERE date = ? AND time = ? AND place = ? AND tg_user_id = ?
        """, (date, time, branch, user_id))

        await db.commit()

    cancel_email(data)

    await callback.message.edit_text("✅ Ваша запись успешно отменена.")
    await callback.answer()