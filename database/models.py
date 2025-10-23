# database/models.py
import sqlite3
from datetime import datetime, timedelta
import aiosqlite
from services.google import get_available_dates_for_branch, connect_to_sheet
import logging

logger = logging.getLogger(__name__)

DB_PATH = "database/scheduler.db"

branches = ["ТРЦ Авиапарк", "ТРЦ Европейский", "ТРЦ Галерея"]

def generate_time_slots():
    times = []
    start_hour = 12
    end_hour = 19
    for hour in range(start_hour, end_hour):
        times.append(f"{hour:02d}:00")
    return times

def parse_date_safe(date_str):
    """
    Пытаемся распознать дату в нескольких популярных форматах.
    Возвращаем datetime.date().
    """
    if date_str is None:
        raise ValueError("Empty date string")

    s = str(date_str).strip()

    fmts = [

     "%m/%d/%Y"
    ]

    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    try:
        num = float(s)
        origin = datetime(1899, 12, 30)
        return (origin + timedelta(days=int(num))).date()
    except Exception:
        pass

    raise ValueError(f"Неподдерживаемый формат даты: {date_str!r}")


def is_same_week(sheet):
    """Проверяем, совпадает ли неделя в Google Sheets с текущей"""
    try:
        dates = get_dates_from_google(sheet)
        if not dates:
            print("[DEBUG] Не найдено дат в Google Sheets")
            return False

        last_date_str = dates[-1]
        print(f"[DEBUG] Последняя дата из таблицы: {last_date_str}")

        last_date = datetime.strptime(last_date_str, "%m/%d/%Y")

        current_start = datetime.now() - timedelta(days=datetime.now().weekday())
        current_end = current_start + timedelta(days=6)
        print(f"[DEBUG] Текущая неделя: {current_start.date()} — {current_end.date()}")

        if current_start.date() <= last_date.date() <= current_end.date():
            print("[DEBUG] ✅ Неделя совпадает.")
            return True
        else:
            print("[DEBUG] ⚠️ Неделя отличается.")
            return False
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке недели: {e}")
        return False


# --- Получение дат из Google Sheets ---
def get_dates_from_google(sheet):
    """Получаем список дат из Google Sheets (с конца таблицы, с логами)"""
    all_values = sheet.get_all_values()
    dates = []

    print(f"[DEBUG] Всего строк в таблице: {len(all_values)}")

    for i, row in enumerate(all_values[1:], start=2): 
        if row and row[0]:
            val = row[0].strip()
            try:
                parsed = datetime.strptime(val, "%m/%d/%Y")
                dates.append(parsed.strftime("%m/%d/%Y"))
            except ValueError:
                try:
                    parsed = datetime.strptime(val, "%d.%m.%Y")
                    dates.append(parsed.strftime("%m/%d/%Y"))
                except ValueError:
                    print(f"[DEBUG] Пропущено значение ({i}): {val}")
                    continue

    print(f"[DEBUG] Распознаны даты: {dates[-7:]}")
    return dates[-7:] 

# --- Инициализация расписания в БД ---
def init_schedule_in_db(dates, branches):
    """Создаёт в БД записи для всех дат и филиалов"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    time_slots = generate_time_slots()

    for branch in branches:
        for date in dates:
            for time in time_slots:
                cursor.execute("""
                    INSERT OR IGNORE INTO tg_schedule (tg_user_id, username, phone, date, time, place)
                    VALUES (NULL, NULL, NULL, ?, ?, ?)
                """, (date, time, branch))

    conn.commit()
    conn.close()

# --- Получение доступных дат ---

def get_available_dates_for_branch(branch):
    sheet = connect_to_sheet()
    rows = sheet.get_all_values()

    if not rows or len(rows) < 2:
        return []

    header = [h.strip() for h in rows[0]]

    try:
        date_idx = header.index("Дата")
        time_idx = header.index("Время")
        branch_idx = header.index("Филиал")
    except ValueError:
        date_idx = next((i for i, h in enumerate(header) if "дат" in h.lower()), None)
        time_idx = next((i for i, h in enumerate(header) if "врем" in h.lower()), None)
        branch_idx = next((i for i, h in enumerate(header) if "фил" in h.lower()), None)

    if None in (date_idx, time_idx, branch_idx):
        return []

    now = datetime.now()
    future_dates = {}

    for row in rows[1:]:
        if len(row) <= max(date_idx, time_idx, branch_idx):
            continue

        row_branch = row[branch_idx].strip()
        if row_branch != branch:
            continue

        date_str = row[date_idx].strip()
        time_str = row[time_idx].strip()

        if not date_str or not time_str:
            continue

        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%m/%d/%Y %H:%M")
        except ValueError:
            continue

        if date_str not in future_dates:
            future_dates[date_str] = []
        future_dates[date_str].append(dt)

    valid_dates = [d for d, times in future_dates.items() if any(t > now for t in times)]
    valid_dates = sorted(valid_dates, key=lambda d: datetime.strptime(d, "%m/%d/%Y"))

    return valid_dates



# --- Получение доступного времени ---
def get_available_times(selected_date: str, branch: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT time FROM tg_schedule
        WHERE date = ? AND place = ? AND tg_user_id IS NULL
        ORDER BY time
    """, (selected_date, branch))
    times = [row[0] for row in cursor.fetchall()]
    conn.close()
    return times

def get_branches_from_google(sheet):
    values = sheet.get_all_values()
    if not values:
        print("[ERROR] Пустая таблица, не удалось получить филиалы.")
        return []

    header = values[0]
    branches = [b.strip() for b in header[2:] if b.strip()]
    print(f"[DEBUG] Все филиалы в шапке: {branches}")

    active_branches = []
    for col_idx, branch in enumerate(branches, start=2):
        for row in values[1:]:
            if len(row) > col_idx and row[col_idx].strip():
                active_branches.append(branch)
                break
    print(f"[DEBUG] Активные филиалы на этой неделе: {active_branches}")
    return active_branches



async def get_branches():
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall("SELECT DISTINCT place FROM tg_schedule")
    return [r[0] for r in rows]

async def get_available_dates(branch: str):
    """
    Возвращает доступные даты для филиала из Google Sheets.
    """
    from asyncio import to_thread
    dates = await to_thread(get_available_dates_for_branch, branch)
    return dates


async def get_available_times(date, branch):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT time FROM tg_schedule WHERE date = ? AND place = ? AND tg_user_id IS NULL ORDER BY time",
            (date, branch)
        )
    return [r[0] for r in rows]