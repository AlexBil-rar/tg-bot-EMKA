import sqlite3
from datetime import datetime

DB_PATH = "database/scheduler.db"

def add_slot(tg_user_id, username, phone, date, time, place):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tg_schedule (tg_user_id, username, phone, date, time, place)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (tg_user_id, username, phone, date, time, place))
    conn.commit()
    conn.close()


def is_slot_available(date, time, place, limit=2):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM tg_schedule
        WHERE date = ? AND time = ? AND place = ?
    """, (date, time, place))
    count = cur.fetchone()[0]
    conn.close()
    return count < limit

def clear_old_slots():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now_date = datetime.now().strftime('%m/%d/%Y')
    now_time = datetime.now().strftime('%H:%M')
    cur.execute("""
        DELETE FROM tg_schedule
        WHERE date < ?
           OR (date = ? AND time < ?)
    """, (now_date, now_date, now_time))
    conn.commit()
    conn.close()
