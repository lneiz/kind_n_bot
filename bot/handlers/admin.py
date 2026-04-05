from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy.future import select
from core.database import async_session, User, Chat, UserChat
from sqlalchemy import update
from config import ADMIN_ID

router = Router()

@router.message(Command("start_prediction_wave"))
async def cmd_start_prediction_wave(message: types.Message):
    """Admin command to reset predictions_count for all users in a chat."""
    # Global admin check
    is_global_admin = message.from_user.id == ADMIN_ID
    
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return
        
    # If not global admin, check if user is chat admin
    if not is_global_admin:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ["creator", "administrator"]:
            await message.answer("Только администратор чата или глобальный админ может запустить волну предсказаний.")
            return
    
    chat_id = message.chat.id
    
    async with async_session() as session:
        # Get all users in this chat
        stmt = select(UserChat.user_id).where(UserChat.chat_id == chat_id)
        result = await session.execute(stmt)
        user_ids = result.scalars().all()
        
        if user_ids:
            # Update predictions_count for these users
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

@router.message(F.text)
async def track_user_in_chat(message: types.Message):
    """Track user-chat association on any message."""
    if message.chat.type in ["group", "supergroup"]:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        async with async_session() as session:
            # Ensure user and chat exist
            # ... (implement user/chat existence check)
            
            # Check if association already exists
            stmt = select(UserChat).where(UserChat.user_id == user_id, UserChat.chat_id == chat_id)
            result = await session.execute(stmt)
            association = result.scalar_one_or_none()
            
            if not association:
                # Need to make sure user and chat are in the DB before creating association
                # Check user
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    user = User(user_id=user_id, first_name=message.from_user.first_name, username=message.from_user.username)
                    session.add(user)
                    
                # Check chat
                stmt = select(Chat).where(Chat.chat_id == chat_id)
                result = await session.execute(stmt)
                chat = result.scalar_one_or_none()
                if not chat:
                    chat = Chat(chat_id=chat_id, title=message.chat.title)
                    session.add(chat)
                
                # Commit user and chat before creating association
                await session.commit()
                
                # Now create association
                new_assoc = UserChat(user_id=user_id, chat_id=chat_id)
                session.add(new_assoc)
                await session.commit()
