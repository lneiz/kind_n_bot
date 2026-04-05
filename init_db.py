import asyncio
from core.database import engine, Base

async def init_db():
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
