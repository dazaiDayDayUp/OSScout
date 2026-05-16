"""
Redis 缓存封装

用于缓存 GitHub API 响应、OSV 查询结果、限频计数等。
Redis 不可用时自动降级（跳过缓存），不打断分析流程。
"""

import json

import redis.asyncio as redis

from app.config import settings

# Redis 连接实例（延迟初始化）
_redis_client: redis.Redis | None = None
# Redis 是否可用（连接失败后置为 False，避免重复尝试）
_redis_available: bool = True


async def get_redis() -> redis.Redis | None:
    """获取或创建 Redis 连接，失败时返回 None"""
    global _redis_client, _redis_available

    if not _redis_available:
        return None

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.redis_url, decode_responses=True
            )
            # 验证连接
            await _redis_client.ping()
        except Exception:
            _redis_available = False
            _redis_client = None

    return _redis_client


async def get_cache(key: str) -> dict | list | None:
    """
    从缓存读取数据
    返回解析后的 JSON 对象，缓存未命中或 Redis 不可用返回 None
    """
    r = await get_redis()
    if r is None:
        return None

    try:
        data = await r.get(key)
        if data is None:
            return None
        return json.loads(data)
    except Exception:
        return None


async def set_cache(key: str, value: dict | list, ttl: int = 86400) -> None:
    """
    写入缓存
    默认 TTL 24 小时（86400 秒）
    Redis 不可用则静默跳过
    """
    r = await get_redis()
    if r is None:
        return

    try:
        await r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


async def delete_cache(key: str) -> None:
    """删除指定缓存，Redis 不可用则静默跳过"""
    r = await get_redis()
    if r is None:
        return

    try:
        await r.delete(key)
    except Exception:
        pass
