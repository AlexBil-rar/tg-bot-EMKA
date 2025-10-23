import asyncio
import logging
import aiocron
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from handlers.start import start_router
from handlers.booking import booking_router
from handlers.back_button import back_router
from handlers.my_booking import my_bookings_router
from handlers.cancel import router as cancel_router

from services.google import connect_to_sheet, _update_branches_periodically
from services.scheduler import send_reminders
from services.schedule_sync import create_week_schedule
from database.models import is_same_week, get_branches_from_google
from config import BOT_TOKEN

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def initialize_schedule():
    logger.info("Подключаемся к Google Sheets...")
    sheet = connect_to_sheet()
    branches = get_branches_from_google(sheet)
    logger.info("Неделя изменилась — создаем новое расписание...")
    await create_week_schedule(branches)
    logger.info("Расписание на неделю обновлено.")

async def main():
    logger.info("Запуск бота...")
    try:
        await initialize_schedule()
    except Exception:
        logger.exception("Ошибка при инициализации расписания")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Роутеры
    dp.include_router(my_bookings_router)
    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(back_router)
    dp.include_router(cancel_router)

    await bot.set_my_commands([BotCommand(command="start", description="Начать работу")])

    # Крон-задачи регистрируем ДО старта поллинга
    @aiocron.crontab("*/2 * * * *")
    async def every_2_min():
        logger.info(f"[CRON] send_reminders @ {datetime.now():%H:%M:%S}")
        await send_reminders(bot)

    @aiocron.crontab("0 0 * * *")
    async def daily_week_check():
        logger.info("Ежедневная проверка недели...")
        sheet = connect_to_sheet()
        if not is_same_week(sheet):
            logger.info("Новая неделя — создаём расписание...")
            await create_week_schedule(get_branches_from_google(sheet))
        else:
            logger.info("Неделя та же — пропускаем.")

    # фоновый апдейтер кэша филиалов
    asyncio.create_task(_update_branches_periodically())

    logger.info("Бот запущен и работает")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
