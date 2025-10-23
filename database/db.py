import os
import sqlite3
from datetime import datetime
import aiosqlite

DB_PATH = os.path.join(os.path.dirname(__file__), "scheduler.db")

def mark_slot_as_taken(date, time, branch, user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE tg_schedule
        SET tg_user_id = ?
        WHERE id IN (
            SELECT id FROM tg_schedule
            WHERE date = ? AND time = ? AND place = ? AND tg_user_id IS NULL
            LIMIT 1
        )
    """, (user_id, date, time, branch))

    conn.commit()
    conn.close()

# Запись бд для уведомления
def save_booking(data: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        INSERT INTO bookings (
            user_id,
            name,
            phone,
            branch,
            date,
            time,
            created_at,
            notified_day_before,
            notified_two_hours_before
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("user_id", 0),
        data["name"],
        data["phone"],
        data["branch"],
        data["date"],
        data["time"],
        datetime.utcnow().isoformat(),
        0,  
        0  
    ))

    conn.commit()
    conn.close()


def generate_time_slots():
    return [f"{h:02d}:00" for h in range(12, 20)]



def get_available_time_slots(place, date, tg_user_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    all_slots = generate_time_slots()
    available = []

    try:
        selected_date = datetime.strptime(date, "%m/%d/%Y").date()
    except ValueError:
        conn.close()
        return []

    now = datetime.now()
    current_date = now.date()
    current_hour = now.hour

    for time in all_slots:
        slot_hour = int(time.split(":")[0])

        if selected_date < current_date:
            continue

        if selected_date == current_date and slot_hour <= current_hour:
            continue

        cursor.execute("""
            SELECT COUNT(*) FROM tg_schedule
            WHERE place = ? AND date = ? AND time = ?
        """, (place, date, time))
        count = cursor.fetchone()[0]

        already_booked = None
        if tg_user_id:
            cursor.execute("""
                SELECT 1 FROM tg_schedule
                WHERE place = ? AND date = ? AND time = ? AND tg_user_id = ?
                LIMIT 1
            """, (place, date, time, tg_user_id))
            already_booked = cursor.fetchone()

        if count < 2 and not already_booked:
            available.append(time)

    conn.close()
    return available


async def save_slot(branch: str, date: str, time: str, tg_user_id: int, username: str, phone: str):
    """Сохраняет запись клиента, если на слот меньше 2 человек."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM tg_schedule WHERE date = ? AND time = ? AND place = ?",
            (date, time, branch)
        )
        count = (await cursor.fetchone())[0]

        if count >= 2:
            return False, f"⚠️ На {time} уже записаны 2 человека. Выберите другое время."

        await db.execute("""
            INSERT INTO tg_schedule (tg_user_id, username, phone, date, time, place)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tg_user_id, username, phone, date, time, branch))
        await db.commit()

    return True, "Запись успешно добавлена!"


async def delete_notified_bookings():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bookings WHERE notified_two_hours_before = 1")
        await db.commit()