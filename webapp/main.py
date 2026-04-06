from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.future import select
from core.database import async_session, User, FavoritePrediction
from core.calculator import calculate_all
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
import httpx
import os
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
    birth_date: str = Form(...),
    gender: int = Form(...),
    first_name: str = Form(None),
    username: str = Form(None)
):
    """Save birth date and generate prediction."""
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
        
        # Save birth date if not already set
        if not user.birth_date:
            user.birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
            user.gender = gender
        
        # Check predictions_count
        if user.predictions_count <= 0:
            return {"error": "У вас закончились предсказания!"}
            
        # Calculate numerology
        data = calculate_all(user.birth_date)
        
        # Generate prediction via DeepSeek
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
            prediction_text = response.json()["choices"][0]["message"]["content"]
            
        # Update predictions_count
        user.predictions_count = 0
        await session.commit()
        
    return templates.TemplateResponse(
        request=request,
        name="prediction.html",
        context={
            "prediction": prediction_text,
            "user_id": user_id
        }
    )

@app.post("/save_favorite")
async def save_favorite(user_id: int = Form(...), content: str = Form(...)):
    """Save prediction to favorites."""
    async with async_session() as session:
        fav = FavoritePrediction(user_id=user_id, content=content)
        session.add(fav)
        await session.commit()
    return {"status": "ok"}
