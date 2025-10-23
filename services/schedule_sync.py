import aiosqlite
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

JSON = "database/telegrambotsheets-475711-529456e3ea7b.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DB_PATH = "database/scheduler.db"

SPREADSHEET_KEY = "1Rf2XoUfTNaWaC2xe094KJdgkP6DKSWhv3T6fQB0Js5Q"
SHEET_NAME = "2025"

def connect_to_sheet():
    creds = Credentials.from_service_account_file(JSON, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
    return sheet

def get_current_week_dates():
    today = datetime.now()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start.date(), end.date()

def is_same_week(sheet):
    try:
        first_date = sheet.cell(2, 1).value 
        if not first_date:
            return False
        first_date = datetime.strptime(first_date, "%m/%d/%Y").date()
        current_start, _ = get_current_week_dates()
        return first_date == current_start
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке недели: {e}")
        return False

async def create_week_schedule(branches):
    """Создаёт расписание на неделю по активным филиалам"""
    now = datetime.now()
    start_date, _ = get_current_week_dates()
    hours = [f"{h:02d}:00" for h in range(12, 20)]

    async with aiosqlite.connect(DB_PATH) as db:
        for i in range(7): 
            if isinstance(start_date, str):
                day_date = datetime.strptime(start_date, "%m/%d/%Y") + timedelta(days=i)
            else:
                day_date = start_date + timedelta(days=i)
            for branch in branches:
                for time in hours:
                    if day_date == now.date() and datetime.strptime(time, "%H:%M").time() <= now.time():
                        continue

                    await db.execute("""
                        INSERT OR IGNORE INTO tg_schedule (tg_user_id, username, phone, date, time, place)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (None, None, None, day_date.strftime('%m/%d/%Y'), time, branch))

        await db.commit()

    print(f"[OK] Расписание на неделю обновлено для {len(branches)} филиалов: {branches}")


async def is_time_available(date, time):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM tg_schedule
            WHERE date = ? AND time = ? AND tg_user_id IS NOT NULL
        """, (date, time)) as cursor:
            (count,) = await cursor.fetchone()
            return count < 2  
        
def get_active_branches_from_gsheet():
    """Возвращает список филиалов, которые сейчас работают (по данным Google Sheets)."""
    gc = gspread.service_account(filename="database/telegrambotsheets-475711-529456e3ea7b.json")
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1Rf2XoUfTNaWaC2xe094KJdgkP6DKSWhv3T6fQB0Js5Q/edit")  # 🔹 вставь свою ссылку
    ws = sh.sheet1

    data = ws.get_all_values()

    branches = data[0][1:]  
    today_str = datetime.now().strftime("%d.%m.%Y")

    active_branches = []

    for row in data[1:]:
        if row[0] == today_str:
            for i, cell in enumerate(row[1:]):
                if cell.strip():  
                    active_branches.append(branches[i])
            break

    return active_branches