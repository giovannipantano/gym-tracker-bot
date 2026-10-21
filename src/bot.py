import sys
import asyncio
import logging

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, TelegramObject, BotCommand
from src.database import init_db
from src.handlers import workout, analytics
from src.config import BOT_TOKEN, ALLOWED_USER_IDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class WhitelistMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if ALLOWED_USER_IDS and isinstance(event, Message):
            if event.from_user.id not in ALLOWED_USER_IDS:
                logging.warning(f"Accesso non autorizzato tentato da ID: {event.from_user.id}")
                return
        return await handler(event, data)

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Guida introduttiva e comandi"),
        BotCommand(command="start_workout", description="Inizia un allenamento"),
        BotCommand(command="fine", description="Termina la sessione corrente"),
        BotCommand(command="annulla", description="Elimina l'ultimo esercizio inserito"),
        BotCommand(command="storico", description="Vedi i workout passati"),
        BotCommand(command="elimina_workout", description="Cancella un workout passato"),
        BotCommand(command="progressione", description="Grafico 1RM (es. /progressione panca)"),
        BotCommand(command="help", description="Mostra spiegazione dettagliata"),
    ]
    await bot.set_my_commands(commands)

import uvicorn
from src.api import app as fastapi_app

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware())
    dp.include_router(workout.router)
    dp.include_router(analytics.router)

    await setup_bot_commands(bot)

    # Configura il server FastAPI sulla porta 8000
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    logging.info("Avvio Bot Telegram + Server PWA sulla porta 8000...")
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot arrestato con successo.")