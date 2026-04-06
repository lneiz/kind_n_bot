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

@router.message(F.new_chat_members)
async def greet_new_chat_members(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        return

    chat_id = message.chat.id
    chat_title = message.chat.title

    new_members = [m for m in (message.new_chat_members or []) if not m.is_bot]
    if not new_members:
        return

    async with async_session() as session:
        stmt = select(Chat).where(Chat.chat_id == chat_id)
        result = await session.execute(stmt)
        chat = result.scalar_one_or_none()

        if not chat:
            chat = Chat(chat_id=chat_id, title=chat_title)
            session.add(chat)
            await session.commit()

        for member in new_members:
            stmt = select(User).where(User.user_id == member.id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                user = User(user_id=member.id, first_name=member.first_name, username=member.username)
                session.add(user)
                await session.commit()

            stmt = select(UserChat).where(UserChat.user_id == member.id, UserChat.chat_id == chat_id)
            result = await session.execute(stmt)
            association = result.scalar_one_or_none()

            if not association:
                session.add(UserChat(user_id=member.id, chat_id=chat_id))
                await session.commit()

    for member in new_members:
        name = f"@{member.username}" if member.username else member.first_name

        reply_markup = None
        if WEB_APP_URL:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🎁 Открыть предсказание",
                    url=f"{WEB_APP_URL}/webapp?user_id={member.id}"
                )]
            ])

        await message.answer(
            f"Привет, {name}! Рады тебе. Держи персональное предсказание на следующую неделю",
            reply_markup=reply_markup
        )
