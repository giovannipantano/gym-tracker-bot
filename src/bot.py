import sys
import asyncio
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, TelegramObject, BotCommand
from src.config import BOT_TOKEN, ALLOWED_USER_ID
from src.database import init_db
from src.handlers import workout, analytics

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class WhitelistMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if ALLOWED_USER_ID and isinstance(event, Message):
            if event.from_user.id != ALLOWED_USER_ID:
                logging.warning(f"Accesso non autorizzato da ID: {event.from_user.id}")
                return
        return await handler(event, data)

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Guida introduttiva e comandi"),
        BotCommand(command="start_workout", description="Inizia un allenamento"),
        BotCommand(command="fine", description="Termina la sessione corrente"),
        BotCommand(command="storico", description="Vedi i workout passati"),
        BotCommand(command="progressione", description="Grafico 1RM (es. /progressione panca)"),
        BotCommand(command="help", description="Mostra spiegazione dettagliata"),
    ]
    await bot.set_my_commands(commands)

async def main():
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.middleware(WhitelistMiddleware())

    # Registra prima analytics (/start, /help, /progressione) e poi workout
    dp.include_router(analytics.router)
    dp.include_router(workout.router)

    await setup_bot_commands(bot)
    logging.info("Comandi del bot registrati nel client Telegram.")

    logging.info("Bot in avvio con Long Polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot arrestato con successo.")