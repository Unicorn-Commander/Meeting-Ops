import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Base
from db_connection import DATABASE_URL, engine

async def init_db():
    # Engine already created in database.py
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully")

if __name__ == "__main__":
    asyncio.run(init_db())
