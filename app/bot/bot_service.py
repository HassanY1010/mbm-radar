from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from app.core.config import settings
from app.core.logging import bot_logger

# Initialize Bot with HTML parse mode
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

# Initialize Dispatcher with Memory FSM Storage
dp = Dispatcher(storage=MemoryStorage())

def setup_bot():
    """Register all bot handlers and middlewares"""
    from app.bot.handlers.user_handlers import user_router
    from app.bot.handlers.admin_handlers import admin_router
    from app.bot.middleware.auth_middleware import SubscriptionMiddleware
    
    # Register middlewares
    user_router.message.outer_middleware(SubscriptionMiddleware())
    user_router.callback_query.outer_middleware(SubscriptionMiddleware())
    
    # Register routers
    dp.include_router(user_router)
    dp.include_router(admin_router)
    
    bot_logger.info("Bot handlers and routers initialized successfully.")
