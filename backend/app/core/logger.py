"""
结构化日志配置
使用 structlog 输出 JSON 格式日志。
"""
import logging
import sys

import structlog

from app.config import settings


def configure_logging():
    """配置全局日志系统"""
    # 设置标准库日志级别
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    # 配置 structlog
    structlog.configure(
        processors=[
            # 添加日志级别
            structlog.stdlib.filter_by_level,
            # 添加时间戳
            structlog.processors.TimeStamper(fmt="iso"),
            # 添加调用位置（文件名和行号）
            structlog.processors.CallsiteParameterAdder(
                [
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            # 格式化异常信息
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.format_exc_info,
            # 输出为 JSON（生产环境）或控制台格式（开发环境）
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """获取命名日志记录器"""
    return structlog.get_logger(name)
