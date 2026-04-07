from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.future import select
from core.database import async_session, User
from core.calculator import calculate_all
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, BOT_TOKEN
from aiogram import Bot
import httpx
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="webapp/templates")
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

@app.get("/webapp")
async def webapp_home(request: Request, user_id: int = None):
    """Render the initial Web App page."""
    user = None

    if user_id:
        async with async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "user_id": user_id
        }
    )

@app.post("/generate_prediction")
async def generate_prediction(
    request: Request,
    user_id: int = Form(...),
    birth_date: str = Form(None),
    gender: int = Form(None),
    first_name: str = Form(None),
    username: str = Form(None)
):
    """Save profile data (if missing) and send prediction to the user in private chat."""
    prediction_text = None

    async with async_session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                user_id=user_id,
                first_name=(first_name or "Пользователь"),
                username=username
            )
            session.add(user)
            await session.commit()
        else:
            changed = False
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if username is not None and user.username != username:
                user.username = username
                changed = True
            if changed:
                await session.commit()

        if not user.birth_date:
            if not birth_date:
                return templates.TemplateResponse(
                    request=request,
                    name="index.html",
                    context={"user": user, "user_id": user_id, "status": "Укажи дату рождения."}
                )
            user.birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
            await session.commit()

        if not user.gender:
            if gender is None:
                return templates.TemplateResponse(
                    request=request,
                    name="index.html",
                    context={"user": user, "user_id": user_id, "status": "Укажи пол."}
                )
            user.gender = gender
            await session.commit()

        if (user.predictions_count or 0) <= 0:
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={"user": user, "user_id": user_id, "status": "У тебя закончились предсказания."}
            )

        data = calculate_all(user.birth_date)

        with open("prompts/prediction.txt", "r", encoding="utf-8") as f:
            prompt_template = f.read()

        gender_label = "не указан"
        if user.gender == 1:
            gender_label = "мужской"
        elif user.gender == 2:
            gender_label = "женский"

        prompt = prompt_template.format(data=str(data))
        prompt = f"{prompt}\n\nПол пользователя: {gender_label}"
        
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
            prediction_text = response.json()["choices"][0]["message"]["content"]

        user.predictions_count = max((user.predictions_count or 0) - 1, 0)
        await session.commit()

    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_message(user_id, prediction_text)
    finally:
        await bot.session.close()

    async with async_session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user, "user_id": user_id, "status": "Готово. Предсказание отправлено в личку бота."}
    )

@app.post("/save_favorite")
async def save_favorite(user_id: int = Form(...), content: str = Form(...)):
    raise HTTPException(status_code=403, detail="disabled")
