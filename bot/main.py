import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from bot.handlers import base, settings, admin

async def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Initialize bot and dispatcher
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Include routers
    dp.include_router(base.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)
    
    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
