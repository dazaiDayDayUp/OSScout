"""
结构化日志配置
使用 structlog 输出对齐的键值对格式日志。

设计要点：
1. 移除时间戳处理器 —— Celery Worker 已在每行开头打印时间戳，避免双重时间戳
2. 移除调用位置处理器 —— 减少日志噪音，故障排查时可通过 logger 名定位
3. 字段排序 —— 固定输出顺序：level → logger → event → 其他字段（字母序）
4. 对齐渲染 —— pad_level=True 让日志级别右对齐，pad_event=35 让事件消息列对齐
"""
import logging
import sys

import structlog

from app.config import settings


class _DropTimestampProcessor:
    """移除 structlog 自动添加的 timestamp 字段

    避免与 Celery Worker 外层日志的时间戳重复，让输出更简洁。
    """

    def __call__(self, logger, method_name, event_dict):
        event_dict.pop("timestamp", None)
        return event_dict


class _SortKeysProcessor:
    """将非核心字段按字母序排序，确保同类型日志的输出顺序一致

    核心字段（event、level、logger）保持原有顺序，其他字段按字母序排列，
    这样同类日志的 key=value 列位置固定，便于快速扫描对比。
    """

    # 核心字段，保持原有顺序
    _CORE_KEYS = ("event", "level", "logger")

    def __call__(self, logger, method_name, event_dict):
        sorted_dict = {}
        # 先放核心字段
        for key in self._CORE_KEYS:
            if key in event_dict:
                sorted_dict[key] = event_dict.pop(key)
        # 再放其他字段（按字母序）
        for key in sorted(sorted(event_dict.keys())):
            sorted_dict[key] = event_dict[key]
        return sorted_dict


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
            # 按级别过滤
            structlog.stdlib.filter_by_level,
            # 添加日志级别字段
            structlog.stdlib.add_log_level,
            # 添加 logger 名字段
            structlog.stdlib.add_logger_name,
            # 格式化异常信息
            structlog.processors.format_exc_info,
            # 移除 timestamp 字段（避免与 Celery 时间戳重复）
            _DropTimestampProcessor(),
            # 字段排序（核心字段在前，其余按字母序）
            _SortKeysProcessor(),
            # 控制台渲染：关闭颜色（Celery Worker 日志通常重定向到文件），
            # pad_level=True 让 [info] [warning] [error] 右对齐，
            # pad_event=35 让事件消息列起始位置对齐
            structlog.dev.ConsoleRenderer(
                colors=False,
                pad_level=True,
                pad_event=35,
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """获取命名日志记录器"""
    return structlog.get_logger(name)
