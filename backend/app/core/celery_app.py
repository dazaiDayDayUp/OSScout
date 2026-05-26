"""
Celery 应用配置

提供异步任务队列的核心入口，底层使用 Redis 作为 Broker。
"""

from celery import Celery

from app.config import settings

# 创建 Celery 应用实例
celery_app = Celery(
    "osscout",
    broker=settings.redis_url,  # Redis 作为消息队列
    backend=settings.redis_url,  # Redis 也作为结果后端
    broker_connection_retry_on_startup=True,  # 启动时自动重试连接
)

# 任务序列化配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # 任务执行超时：5 分钟（和 analysis_timeout 一致）
    task_time_limit=300,
    # 任务软超时：4 分钟（先抛 SoftTimeLimitExceeded 给优雅处理机会）
    task_soft_time_limit=240,
    # 禁止 Celery 劫持 root logger，避免 structlog 日志级别被错误标记为 WARNING
    worker_hijack_root_logger=False,
)

# 显式导入任务模块，确保 Celery 注册任务
# autodiscover_tasks 适用于 Django，纯 FastAPI 项目需手动导入
import app.tasks.analysis_tasks  # noqa: F401
import app.tasks.email_tasks  # noqa: F401
