import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

DB_PATH = "database/scheduler.db"

TOLERANCE = timedelta(minutes=2)

async def send_reminders(bot: Bot):
    now = datetime.now()

    async with aiosqlite.connect(DB_PATH) as db:
        # --- БЛОК: РОВНО ЗА 24 ЧАСА ---
        async with db.execute("""
            SELECT id, user_id, name, date, time
            FROM bookings
            WHERE notified_day_before = 0
        """) as cursor:
            rows = await cursor.fetchall()

        for appointment_id, user_id, name, appt_date, appt_time in rows:
            try:
                appt_dt = datetime.strptime(f"{appt_date} {appt_time}", "%m/%d/%Y %H:%M")

                diff_hours = (appt_dt - now).total_seconds() / 3600
                if 24 <= diff_hours <= 24.3:
                    display_date = datetime.strptime(appt_date, "%m/%d/%Y").strftime("%d-%m-%Y")
                    msg = f"📅 Привет, {name}!\nНапоминаем, что вы записаны завтра — {display_date} в {appt_time}."

                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_{appointment_id}")
                        ]]
                    )

                    await bot.send_message(chat_id=user_id, text=msg, reply_markup=kb)
                    await db.execute("UPDATE bookings SET notified_day_before = 1 WHERE id = ?", (appointment_id,))
                    await db.commit()
                    print(f"[OK] 24h reminder sent (id={appointment_id}, diff={diff_hours:.2f}h)")

                elif diff_hours < 23.5:
                    await db.execute("UPDATE bookings SET notified_day_before = 1 WHERE id = ?", (appointment_id,))
                    await db.commit()
                    print(f"[SKIP] Missed 24h window (id={appointment_id}, diff={diff_hours:.2f}h)")


            except Exception as e:
                print(f"❌ Error 24h reminder id={appointment_id}: {e}")

        # --- БЛОК: ЗА 2 ЧАСА ---
        TW_TOL = timedelta(minutes=5)

        async with db.execute("""
            SELECT id, user_id, name, date, time
            FROM bookings
            WHERE notified_two_hours_before = 0
        """) as cursor:
            rows = await cursor.fetchall()

        for appointment_id, user_id, name, appt_date, appt_time in rows:
            try:
                appt_dt = datetime.strptime(f"{appt_date} {appt_time}", "%m/%d/%Y %H:%M")
                target = appt_dt - timedelta(hours=2)

                if (target - TW_TOL) <= now <= (target + TW_TOL):
                    msg = f"⏰ Привет, {name}!\nЧерез 2 часа у вас запись в {appt_time}."
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_{appointment_id}")
                        ]]
                    )

                    await bot.send_message(chat_id=user_id, text=msg, reply_markup=kb)
                    await db.execute(
                        "UPDATE bookings SET notified_two_hours_before = 1 WHERE id = ?",
                        (appointment_id,)
                    )
                    await db.commit()
                    print(f"[OK] 2h reminder sent (id={appointment_id}, target={target.time()})")

                elif now > (target + TW_TOL):
                    await db.execute(
                        "UPDATE bookings SET notified_two_hours_before = 1 WHERE id = ?",
                        (appointment_id,)
                    )
                    await db.commit()
                    print(f"[SKIP] 2h window missed, flag set (id={appointment_id})")

            except Exception as e:
                print(f"❌ Error 2h reminder id={appointment_id}: {e}")

        # --- ЧИСТКА bookings в течение первых 5 минут с начала часа записи ---
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        current_hour_end = current_hour_start + timedelta(minutes=5)

        async with db.execute("SELECT id, date, time FROM bookings") as cursor:
            rows = await cursor.fetchall()

        for appointment_id, appt_date, appt_time in rows:
            try:
                appt_dt = datetime.strptime(f"{appt_date} {appt_time}", "%m/%d/%Y %H:%M")
                if current_hour_start <= appt_dt < current_hour_end:
                    await db.execute("DELETE FROM bookings WHERE id = ?", (appointment_id,))
                    await db.commit()
                    print(f"[DEL] Booking removed (id={appointment_id})")
            except Exception as e:
                print(f"❌ Cleanup bookings error id={appointment_id}: {e}")

        async with db.execute("SELECT date, time, place, tg_user_id FROM tg_schedule") as cursor:
            schedule_rows = await cursor.fetchall()

        deleted_slots = 0
        for appt_date, appt_time, branch, tg_user_id in schedule_rows:
            try:
                appt_dt = datetime.strptime(f"{appt_date} {appt_time}", "%m/%d/%Y %H:%M")
                if appt_dt <= now:
                    await db.execute(
                        "DELETE FROM tg_schedule WHERE date = ? AND time = ? AND place = ? AND tg_user_id = ?",
                        (appt_date, appt_time, branch, tg_user_id)
                    )
                    deleted_slots += 1
            except Exception as e:
                print(f"❌ Cleanup schedule error: {e}")

        if deleted_slots:
            await db.commit()
            print(f"[CLEANUP] Removed {deleted_slots} old slots from tg_schedule")
