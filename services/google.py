import os
import logging
import asyncio
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

JSON = "database/neon-metric-474307-c8-6393a2c845a2.json"
SPREADSHEET_KEY = "1ApDopfE1LrZzdGIf6JhH_hncp0-pbrp7gzw2usfsPok"
SHEET_NAME = "2025"

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
logging.basicConfig(level=logging.DEBUG if DEBUG_MODE else logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def connect_to_sheet():
    """Подключение и возврат worksheet"""
    creds = Credentials.from_service_account_file(JSON, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
    logger.debug("[DEBUG] Листы в таблице:")
    for ws in client.open_by_key(SPREADSHEET_KEY).worksheets():
        logger.debug(" - " + ws.title)
    return sheet

def _parse_date_cell(val):
    """Пытаемся распарсить дату в ячейке (несколько форматов + excel-serial). Возвращаем datetime.date или None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    fmts = ["%m/%d/%Y", "%m/%d/%y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except Exception:
            pass

    try:
        num = float(s)
        origin = datetime(1899, 12, 30)
        return (origin + timedelta(days=int(num))).date()
    except Exception:
        pass

    return None


def get_active_branches_from_gsheet(sheet=None):
    """
    Возвращает список филиалов, у которых есть хоть одно заполнение
    в ЛЮБОЙ строке текущей недели (пн-вс).
    """
    try:
        if sheet is None:
            sheet = connect_to_sheet()

        rows = sheet.get_all_values()
        if not rows:
            logger.debug("Пустая таблица.")
            return []

        header_idx = None
        for i, row in enumerate(rows):
            low = [c.strip().lower() for c in row]
            if any(x in low for x in ("дата", "д/н", "date")):
                header_idx = i
                break
        if header_idx is None:
            logger.warning("Не нашли строку заголовка с 'дата'/'д/н'.")
            return []

        header = rows[header_idx]
        start_idx = 2 if len(header) >= 3 else 1
        idx2name = {start_idx + i: name.strip()
                    for i, name in enumerate(header[start_idx:])
                    if name and name.strip()}
        header_order = list(idx2name.values())
        logger.debug(f"[HEADER] Филиалы в шапке: {header_order}")

        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        logger.debug(f"[DEBUG] Неделя: {week_start} — {week_end}")

        active = set()
        for row in rows[header_idx + 1:]:
            if not row:
                continue
            parsed = _parse_date_cell(row[0] if len(row) > 0 else "")
            if not parsed:
                continue

            if parsed < week_start:
                continue              
            if parsed > week_end:
                break                 

            for col_idx, name in idx2name.items():
                if col_idx < len(row) and row[col_idx].strip():
                    active.add(name)

        if not active:
            logger.info("⚠️ В текущей неделе нет заполненных филиалов — возвращаем все из шапки.")
            active = set(header_order)

        result = [name for name in header_order if name in active]
        logger.info(f"Активные филиалы за текущую неделю: {result}")
        return result

    except Exception:
        logger.exception("Ошибка при получении филиалов из Google Sheets:")
        return []
    

def get_available_dates_for_branch(branch_name, sheet=None):
    """
    Возвращает список дат для конкретного филиала за текущую неделю,
    убирая все прошедшие дни (и сегодняшний, если уже прошли все слоты).
    """
    try:
        if sheet is None:
            sheet = connect_to_sheet()

        all_rows = sheet.get_all_values()
        if not all_rows or len(all_rows) < 2:
            logger.warning("Таблица пуста или некорректна.")
            return []

        header_idx = None
        for i, row in enumerate(all_rows):
            low = [c.strip().lower() for c in row]
            if any(x in low for x in ("дата", "д/н", "date")):
                header_idx = i
                break
        if header_idx is None:
            logger.warning("Не удалось найти строку заголовка.")
            return []

        header = all_rows[header_idx]
        start_idx = 2 if len(header) >= 3 else 1
        header_branches = [h.strip() for h in header[start_idx:] if h.strip()]

        if branch_name not in header_branches:
            logger.warning(f"⚠️ Филиал '{branch_name}' не найден в шапке.")
            return []

        branch_col_idx = start_idx + header_branches.index(branch_name)

        today = datetime.now().date()
        now_time = datetime.now().time()

        available_dates = {}
        for row in all_rows[header_idx + 1:]:
            if len(row) <= branch_col_idx:
                continue

            date_str = row[0].strip() if row[0] else ""
            parsed = _parse_date_cell(date_str)
            if not parsed:
                continue

            cell_val = row[branch_col_idx].strip()
            if not cell_val:
                continue

            available_dates.setdefault(parsed, True)

        filtered_dates = []
        for date_obj in sorted(available_dates.keys()):
            if date_obj < today:
                continue
            if date_obj == today and now_time >= datetime.strptime("19:00", "%H:%M").time():
                continue
            filtered_dates.append(date_obj.strftime("%m/%d/%Y"))

        logger.info(f"Для филиала '{branch_name}' актуальные даты: {filtered_dates}")
        return filtered_dates

    except Exception:
        logger.exception("Ошибка при получении дат филиала:")
        return []

# Глобальный кэш
_cached_branches = []
_last_update = 0


def _fetch_active_branches():
    """
    Внутренняя функция: реально запрашивает данные у Google Sheets.
    """
    try:
        sheet = connect_to_sheet()
        all_rows = sheet.get_values("A1:Z")  
        if not all_rows or len(all_rows) < 2:
            return []

        header_idx = None
        for i, row in enumerate(all_rows):
            low = [c.strip().lower() for c in row]
            if any(x in low for x in ("дата", "д/н", "date")):
                header_idx = i
                break
        if header_idx is None:
            return []

        header = all_rows[header_idx]
        start_idx = 2 if len(header) >= 3 else 1
        branches = [h.strip() for h in header[start_idx:] if h.strip()]

        today = datetime.now().date()
        now_time = datetime.now().time()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        active = {branch: False for branch in branches}

        for row in reversed(all_rows[header_idx + 1:]):
            if not row or not row[0]:
                continue
            parsed = _parse_date_cell(row[0])
            if not parsed:
                continue

            if parsed < week_start:
                continue

            if not (week_start <= parsed <= week_end):
                continue

            for i, branch in enumerate(branches, start=start_idx):
                if i < len(row) and row[i].strip():
                    if parsed == today and now_time >= datetime.strptime("19:00", "%H:%M").time():
                        continue
                    active[branch] = True


        valid_branches = [b for b, v in active.items() if v]
        logger.info(f"Активные филиалы: {valid_branches}")
        return valid_branches

    except Exception:
        logger.exception("Ошибка при получении активных филиалов:")
        return []


async def _update_branches_periodically():
    """
    обновляет данные каждые 30 секунд.
    """
    global _cached_branches, _last_update
    while True:
        _cached_branches = _fetch_active_branches()
        _last_update = datetime.now().timestamp()
        await asyncio.sleep(30)  # обновляем каждые 30 секунд


def get_active_branches():
    """
    Возвращает кэшированные филиалы мгновенно.
    """
    global _cached_branches, _last_update

    if _cached_branches and datetime.now().timestamp() - _last_update < 60:
        return _cached_branches

    branches = _fetch_active_branches()
    _cached_branches = branches
    _last_update = datetime.now().timestamp()
    return branches

