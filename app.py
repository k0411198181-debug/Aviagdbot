import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot_admin_handlers import router as admin_router
from bot_handlers import router
from config import BOT_TOKEN, CHECK_INTERVAL, LOG_LEVEL
from db_models import init_db
from services_aviasales import set_http_session
from services_monitor import check_all_alerts

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    init_db()
    logger.info("БД инициализирована")

    http_session = aiohttp.ClientSession()
    set_http_session(http_session)
    logger.info("HTTP сессия создана")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.include_router(admin_router)

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        check_all_alerts, "interval",
        seconds=CHECK_INTERVAL, args=[bot],
        id="alerts", max_instances=1, coalesce=True,
    )
    scheduler.start()
    logger.info("✈️🚂 TicketRadar запущен (интервал проверки алертов: %ds)", CHECK_INTERVAL)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await http_session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
