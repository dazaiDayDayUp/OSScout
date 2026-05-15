"""
数据库连接与会话管理
使用 SQLAlchemy 异步引擎 + asyncpg 驱动
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.core.models import Base

# 创建异步数据库引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # debug 模式下打印 SQL 语句
    future=True,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db():
    """
    依赖注入用的数据库会话生成器
    FastAPI 的 Depends 会调用这个函数获取会话
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """
    初始化数据库，创建所有表
    通常在应用启动时调用一次
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
