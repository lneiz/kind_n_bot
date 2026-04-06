from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy.future import select
from sqlalchemy import update, func
from core.database import async_session, User, Chat, UserChat
from config import ADMIN_ID, WEB_APP_URL

WEB_APP_BASE_URL = (WEB_APP_URL or "").rstrip("/")
if WEB_APP_BASE_URL.endswith("/webapp"):
    WEB_APP_BASE_URL = WEB_APP_BASE_URL[: -len("/webapp")]

router = Router()

async def _is_chat_admin_or_global(message: types.Message) -> bool:
    if message.from_user.id == ADMIN_ID:
        return True

    if message.chat.type not in ["group", "supergroup"]:
        return False

    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ["creator", "administrator"]

@router.message(Command("start_prediction_wave"))
async def cmd_start_prediction_wave(message: types.Message):
    """Admin command to reset predictions_count for all users in a chat."""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return

    if not await _is_chat_admin_or_global(message):
        await message.answer("Только администратор чата или глобальный админ может запустить волну предсказаний.")
        return

    chat_id = message.chat.id

    async with async_session() as session:
        stmt = select(UserChat.user_id).where(UserChat.chat_id == chat_id)
        result = await session.execute(stmt)
        user_ids = result.scalars().all()

        if user_ids:
            update_stmt = (
                update(User)
                .where(User.user_id.in_(user_ids))
                .values(predictions_count=1)
            )
            await session.execute(update_stmt)
            await session.commit()

    await message.answer(
        f"Волна предсказаний запущена! Все {len(user_ids)} участников получили по одному предсказанию 🏕"
    )

@router.message(Command("offer_prediction"))
async def cmd_offer_prediction(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return

    if not await _is_chat_admin_or_global(message):
        await message.answer("Только администратор чата или глобальный админ может использовать эту команду.")
        return

    if not WEB_APP_BASE_URL:
        await message.answer("WEB_APP_URL не настроен.")
        return

    webapp_url = f"{WEB_APP_BASE_URL}/webapp"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎁 Открыть предсказание",
            web_app=WebAppInfo(url=webapp_url)
        )]
    ])

    try:
        await message.answer(
            "Кому нужен прогноз — нажмите кнопку ниже. Веб‑приложение откроется прямо в Telegram.",
            reply_markup=keyboard
        )
    except TelegramBadRequest as e:
        if "BUTTON_TYPE_INVALID" not in str(e):
            raise

        fallback = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть по ссылке", url=webapp_url)]
        ])

        await message.answer(
            "Telegram не принял WebApp‑кнопку в этом чате. Откройте по ссылке:",
            reply_markup=fallback
        )

@router.message(Command("add_predictions"))
async def cmd_add_predictions(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return

    if not await _is_chat_admin_or_global(message):
        await message.answer("Только администратор чата или глобальный админ может использовать эту команду.")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /add_predictions @username [кол-во]")
        return

    username = parts[1].lstrip("@").strip()
    if not username:
        await message.answer("Использование: /add_predictions @username [кол-во]")
        return

    count = 1
    if len(parts) >= 3:
        try:
            count = int(parts[2])
        except ValueError:
            await message.answer("Кол-во должно быть числом. Пример: /add_predictions @username 2")
            return

    if count <= 0:
        await message.answer("Кол-во должно быть положительным числом.")
        return

    async with async_session() as session:
        stmt = select(User).where(User.username == username)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(f"Пользователь @{username} не найден в базе.")
            return

        user.predictions_count = (user.predictions_count or 0) + count
        await session.commit()

    await message.answer(f"@{username}: +{count} (теперь {user.predictions_count}).")

@router.message(Command("add_predictions_all"))
async def cmd_add_predictions_all(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return

    if not await _is_chat_admin_or_global(message):
        await message.answer("Только администратор чата или глобальный админ может использовать эту команду.")
        return

    parts = (message.text or "").split(maxsplit=1)
    count = 1
    if len(parts) == 2:
        try:
            count = int(parts[1])
        except ValueError:
            await message.answer("Кол-во должно быть числом. Пример: /add_predictions_all 1")
            return

    if count <= 0:
        await message.answer("Кол-во должно быть положительным числом.")
        return

    chat_id = message.chat.id

    async with async_session() as session:
        stmt = select(UserChat.user_id).where(UserChat.chat_id == chat_id)
        result = await session.execute(stmt)
        user_ids = result.scalars().all()

        if not user_ids:
            await message.answer("В базе нет участников, привязанных к этому чату.")
            return

        update_stmt = (
            update(User)
            .where(User.user_id.in_(user_ids))
            .values(predictions_count=func.coalesce(User.predictions_count, 0) + count)
        )
        await session.execute(update_stmt)
        await session.commit()

    await message.answer(f"Всем участникам чата добавлено +{count} к predictions_count (участников: {len(user_ids)}).")

@router.message(F.text)
async def track_user_in_chat(message: types.Message):
    """Track user-chat association on any message."""
    if message.chat.type in ["group", "supergroup"]:
        user_id = message.from_user.id
        chat_id = message.chat.id

        async with async_session() as session:
            stmt = select(UserChat).where(UserChat.user_id == user_id, UserChat.chat_id == chat_id)
            result = await session.execute(stmt)
            association = result.scalar_one_or_none()

            if not association:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    user = User(user_id=user_id, first_name=message.from_user.first_name, username=message.from_user.username)
                    session.add(user)

                stmt = select(Chat).where(Chat.chat_id == chat_id)
                result = await session.execute(stmt)
                chat = result.scalar_one_or_none()
                if not chat:
                    chat = Chat(chat_id=chat_id, title=message.chat.title)
                    session.add(chat)

                await session.commit()

                new_assoc = UserChat(user_id=user_id, chat_id=chat_id)
                session.add(new_assoc)
                await session.commit()
