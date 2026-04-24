from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands


DEFAULT_BOT_COMMANDS = [
    BotCommand(command="start", description="نمایش منوی اصلی"),
]


async def setup_bot_menu(bot: Bot):
    await bot.set_my_commands(DEFAULT_BOT_COMMANDS)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
