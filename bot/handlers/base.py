from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from core.database import async_session, User, Chat, UserChat
from core.calculator import calculate_all
from config import WEB_APP_URL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, ADMIN_ID
import httpx
from datetime import datetime

router = Router()

WEB_APP_BASE_URL = (WEB_APP_URL or "").rstrip("/")
if WEB_APP_BASE_URL.endswith("/webapp"):
    WEB_APP_BASE_URL = WEB_APP_BASE_URL[: -len("/webapp")]

async def _generate_prediction_text(birth_date):
    data = calculate_all(birth_date)

    with open("prompts/prediction.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(data=str(data))

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Ты — сосед-путешественник. Используй данные для ироничного совета на путь. Без магии."},
                    {"role": "user", "content": prompt}
                ]
            }
        )

    return response.json()["choices"][0]["message"]["content"]

@router.message(CommandStart())
def _not_ready_text(user: User) -> str:
    if user.gender == 2:
        return "Подруга, ты пока не готова к предсказанию. Я сообщу, когда придет время"
    return "Друг, ты пока не готов к предсказанию. Я сообщу, когда придет время"

async def cmd_start(message: types.Message):
    """Handle /start command."""
    start_payload = None
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2:
            start_payload = parts[1].strip()

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
        else:
            changed = False
            if user.first_name != message.from_user.first_name:
                user.first_name = message.from_user.first_name
                changed = True
            if user.username != message.from_user.username:
                user.username = message.from_user.username
                changed = True
            if changed:
                await session.commit()

        if message.chat.type in ["group", "supergroup"]:
            me = await message.bot.get_me()
            keyboard = None
            if me.username:
                url = f"https://t.me/{me.username}?start=offer"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть бота", url=url)]
                ])

            await message.answer(
                "Открой меня в личке, чтобы получить предсказание. В группе админ может настроить таймзону командой /timezone.",
                reply_markup=keyboard
            )
            return

        if message.chat.type != "private" and message.chat.type is not None:
            await message.answer("Открой меня в личке и нажми /start.")
            return

        has_profile = bool(user.birth_date) and bool(user.gender)
        if not has_profile:
            if not WEB_APP_BASE_URL:
                await message.answer("WEB_APP_URL не настроен.")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📝 Заполнить анкету",
                    web_app=WebAppInfo(url=f"{WEB_APP_BASE_URL}/webapp?user_id={message.from_user.id}")
                )]
            ])

            text = "Чтобы я дал персональное предсказание, заполни анкету:"
            if start_payload == "offer":
                text = "Чтобы я дал персональное предсказание, сначала заполни анкету:"

            await message.answer(
                text,
                reply_markup=keyboard
            )
            return

        if (user.predictions_count or 0) <= 0:
            await message.answer(_not_ready_text(user))
            return

        prediction_text = await _generate_prediction_text(user.birth_date)
        user.predictions_count = max((user.predictions_count or 0) - 1, 0)
        await session.commit()

    await message.answer(prediction_text)

@router.message(F.text)
async def private_lockdown(message: types.Message):
    if message.chat.type != "private":
        return

    if message.from_user.id == ADMIN_ID:
        return

    text = message.text or ""
    if text.startswith("/start"):
        return

    return

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
