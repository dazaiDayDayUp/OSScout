#!/usr/bin/env python3
"""
创建 benchmark_data 表

绕过 Alembic 编码问题，直接用 SQLAlchemy create_all() 创建。
使用前确保数据库服务已启动（docker-compose up db）。
"""

import asyncio
import sys
from pathlib import Path

# 添加 backend 到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings
from app.core.models import Base


async def main():
    """异步创建表"""
    print(f"数据库地址: {settings.database_url}")
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        # 只创建不存在的表（不会删除已有表）
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("表创建完成（已存在的表会跳过）")


if __name__ == "__main__":
    asyncio.run(main())
