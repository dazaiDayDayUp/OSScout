"""
Redis 缓存封装
用于缓存 GitHub API 响应、限频计数等
"""
import json

import redis.asyncio as redis

from app.config import settings

# Redis 连接实例（延迟初始化）
_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """获取或创建 Redis 连接"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def get_cache(key: str) -> dict | list | None:
    """
    从缓存读取数据
    返回解析后的 JSON 对象，缓存未命中返回 None
    """
    r = await get_redis()
    data = await r.get(key)
    if data is None:
        return None
    return json.loads(data)


async def set_cache(key: str, value: dict | list, ttl: int = 86400) -> None:
    """
    写入缓存
    默认 TTL 24 小时（86400 秒）
    """
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value))


async def delete_cache(key: str) -> None:
    """删除指定缓存"""
    r = await get_redis()
    await r.delete(key)
