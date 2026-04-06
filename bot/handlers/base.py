from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from core.database import async_session, User, Chat, UserChat
from config import WEB_APP_URL

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handle /start command."""
    async with async_session() as session:
        stmt = select(User).where(User.user_id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                user_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username
            )
            session.add(user)
            await session.commit()

    if message.chat.type in ["group", "supergroup"]:
        await message.answer(
            "Я работаю с предсказаниями через личные сообщения. Открой меня в личке и нажми /start. "
            "Для работы в группе админ может настроить таймзону командой /timezone."
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎁 Получить предсказание",
            web_app=WebAppInfo(url=f"{WEB_APP_URL}/webapp?user_id={message.from_user.id}")
        )]
    ])

    try:
        await message.answer(
            f"Привет, {message.from_user.first_name}! Я твой дружелюбный сосед-путешественник.\n\n"
            "Заполни анкету в моем приложении, чтобы я мог рассчитать твою матрицу судьбы и "
            "сделать для тебя особенное предсказание!",
            reply_markup=keyboard
        )
    except TelegramBadRequest as e:
        if "BUTTON_TYPE_INVALID" not in str(e):
            raise
        await message.answer(
            "Открой меня в личке и нажми /start, чтобы получить предсказание."
        )

@router.my_chat_member(F.new_chat_member.status == "member")
async def bot_added_to_group(event: types.ChatMemberUpdated):
    """Handle bot added to group."""
    chat_id = event.chat.id
    chat_title = event.chat.title
    
    async with async_session() as session:
        # Add chat to database
        stmt = select(Chat).where(Chat.chat_id == chat_id)
        result = await session.execute(stmt)
        chat = result.scalar_one_or_none()
        
        if not chat:
            chat = Chat(chat_id=chat_id, title=chat_title)
            session.add(chat)
            await session.commit()
            
    await event.bot.send_message(
        chat_id,
        f"Всем привет! Я — ваш новый сосед-путешественник 🏕\n\n"
        "Админ, пожалуйста, настрой временную зону чата с помощью команды /timezone, "
        "чтобы я знал, когда приходить с поздравлениями!"
    )
