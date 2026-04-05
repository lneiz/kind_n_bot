from datetime import datetime
from sqlalchemy import BigInteger, Column, String, Date, Time, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from config import DATABASE_URL

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(BigInteger, primary_key=True)
    first_name = Column(String, nullable=False)
    username = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    birth_time = Column(Time, nullable=True)
    gender = Column(Integer, nullable=True)  # 1 for male, 2 for female
    predictions_count = Column(Integer, default=1)
    
    chats = relationship("Chat", secondary="user_chats", back_populates="users")
    favorites = relationship("FavoritePrediction", back_populates="user")

class Chat(Base):
    __tablename__ = 'chats'
    
    chat_id = Column(BigInteger, primary_key=True)
    title = Column(String, nullable=False)
    timezone = Column(String, default='UTC')
    is_active = Column(Boolean, default=True)
    
    users = relationship("User", secondary="user_chats", back_populates="chats")

class UserChat(Base):
    __tablename__ = 'user_chats'
    
    user_id = Column(BigInteger, ForeignKey('users.user_id'), primary_key=True)
    chat_id = Column(BigInteger, ForeignKey('chats.chat_id'), primary_key=True)

class FavoritePrediction(Base):
    __tablename__ = 'favorite_predictions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="favorites")

# Database engine and sessionmaker setup
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session
