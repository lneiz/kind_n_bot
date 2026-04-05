from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from core.database import async_session, Chat
import pytz

router = Router()

POPULAR_TIMEZONES = [
    "UTC",
    "Europe/Moscow",
    "Asia/Yekaterinburg",
    "Asia/Almaty",
    "Asia/Tashkent",
    "Europe/Kaliningrad",
    "Asia/Novosibirsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok"
]

@router.message(Command("timezone"))
async def cmd_timezone(message: types.Message):
    """Command to set timezone in a chat."""
    # Check if user is admin
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return
        
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer("Только администратор чата может менять настройки.")
        return
    
    # Generate keyboard
    keyboard_buttons = []
    for tz in POPULAR_TIMEZONES:
        keyboard_buttons.append([InlineKeyboardButton(text=tz, callback_data=f"set_tz:{tz}")])
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(
        "Выберите временную зону для этого чата:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("set_tz:"))
async def process_set_tz(callback: types.CallbackQuery):
    """Handle timezone selection."""
    tz = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    
    async with async_session() as session:
        stmt = select(Chat).where(Chat.chat_id == chat_id)
        result = await session.execute(stmt)
        chat = result.scalar_one_or_none()
        
        if not chat:
            chat = Chat(chat_id=chat_id, title=callback.message.chat.title)
            session.add(chat)
            
        chat.timezone = tz
        await session.commit()
        
    await callback.message.edit_text(f"Временная зона для чата установлена: {tz}")
    await callback.answer()
