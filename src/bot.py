import asyncio
import logging
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, TelegramObject
from src.config import BOT_TOKEN, ALLOWED_USER_ID
from src.database import init_db
from src.handlers import workout, analytics
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class WhitelistMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if ALLOWED_USER_ID and isinstance(event, Message):
            if event.from_user.id != ALLOWED_USER_ID:
                logging.warning(f"Accesso non autorizzato tentato da ID: {event.from_user.id}")
                return
        return await handler(event, data)

async def main():
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Protezione del bot a solo uso personale
    dp.message.middleware(WhitelistMiddleware())

    # Registrazione router
    dp.include_router(workout.router)
    dp.include_router(analytics.router)

    logging.info("Bot in avvio con Long Polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot arrestato con successo.")