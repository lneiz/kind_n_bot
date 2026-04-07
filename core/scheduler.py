import asyncio
import logging
from datetime import datetime, date
import pytz
from sqlalchemy.future import select
from core.database import async_session, User, Chat, UserChat
from core.calculator import calculate_all
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, BOT_TOKEN
import httpx
from aiogram import Bot

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_birthday_users(session, chat_id, local_today):
    """Find users in a specific chat who have a birthday on local_today."""
    stmt = (
        select(User, UserChat)
        .join(UserChat, UserChat.user_id == User.user_id)
        .where(UserChat.chat_id == chat_id)
        .where(User.birth_date != None)
    )
    result = await session.execute(stmt)
    rows = result.all()

    birthday_rows = []
    for user, assoc in rows:
        if user.birth_date.month == local_today.month and user.birth_date.day == local_today.day:
            birthday_rows.append((user, assoc))

    return birthday_rows

def _gender_label(gender) -> str:
    if gender == 1:
        return "мужской"
    if gender == 2:
        return "женский"
    return "не указан"

async def generate_birthday_greeting(user, bot_name):
    """Generate a birthday greeting using DeepSeek."""
    data = calculate_all(user.birth_date)
    
    with open("prompts/birthday.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()
        
    prompt = prompt_template.format(name=user.first_name, data=str(data))
    prompt = f"{prompt}\n\nПол: {_gender_label(user.gender)}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Поздравь друга с ДР. Подсвети его черты по цифрам, сделай это провокационно, чтобы чат оживился. Используй метафоры дорог и походов."},
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=30.0
            )
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error generating birthday greeting for {user.user_id}: {e}")
            return f"С днем рождения, {user.first_name}! 🏕 Пусть твой путь будет легким!"

async def run_scheduler():
    """Main scheduler loop."""
    bot = Bot(token=BOT_TOKEN)
    
    while True:
        now_utc = datetime.now(pytz.utc)
        
        async with async_session() as session:
            # Get all active chats
            stmt = select(Chat).where(Chat.is_active == True)
            result = await session.execute(stmt)
            chats = result.scalars().all()
            
            for chat in chats:
                try:
                    # Check local time for the chat
                    tz = pytz.timezone(chat.timezone or 'UTC')
                    local_time = now_utc.astimezone(tz)
                    
                    # Trigger once within 09:00–09:59 local time
                    if local_time.hour == 9:
                        logger.info(f"Processing chat {chat.chat_id} (timezone {chat.timezone})")
                        
                        local_today = local_time.date()
                        birthday_rows = await get_birthday_users(session, chat.chat_id, local_today)

                        local_year = local_today.year
                        for user, assoc in birthday_rows:
                            if assoc.last_birthday_greeted_year == local_year:
                                continue

                            greeting = await generate_birthday_greeting(user, "Сосед-путешественник")

                            mention = f"[{user.first_name}](tg://user?id={user.user_id})"
                            message_text = f"🏕 {greeting}\n\nПоздравляем нашего попутчика {mention}! 🎒👟"

                            await bot.send_message(chat.chat_id, message_text, parse_mode="Markdown")

                            assoc.last_birthday_greeted_year = local_year
                            await session.commit()

                            await asyncio.sleep(2)
                            
                except Exception as e:
                    logger.error(f"Error processing chat {chat.chat_id}: {e}")
        
        # Sleep for 1 minute before next check
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(run_scheduler())
