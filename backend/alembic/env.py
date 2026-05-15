"""
Alembic 迁移环境脚本
负责连接数据库、加载模型元数据、执行迁移操作
支持异步数据库连接
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 导入应用配置和模型基类
from app.config import settings
from app.core.models import Base

# Alembic 配置对象
config = context.config

# 使用应用的数据库连接地址覆盖配置文件中的默认值
config.set_main_option("sqlalchemy.url", settings.database_url)

# 配置日志（如果配置文件存在）
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据 — Alembic 会对比这个元数据和数据库实际结构，生成迁移脚本
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    离线模式运行迁移
    不需要实际连接数据库，直接生成 SQL 脚本
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在数据库连接上执行迁移"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步模式运行迁移"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    在线模式运行迁移
    需要实际连接数据库执行 DDL 操作
    """
    asyncio.run(run_async_migrations())


# 根据是否有数据库连接，选择离线或在线模式
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
