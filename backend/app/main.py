"""
FastAPI 应用入口
整个后端服务的启动点，注册路由、中间件、异常处理
"""
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.database import init_db
from app.core.logger import configure_logging, get_logger

# 获取应用日志记录器
logger = get_logger("osscout.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化日志和数据库表结构
    """
    configure_logging()
    logger.info("应用启动中", version="0.1.0")
    await init_db()
    logger.info("数据库初始化完成")
    yield
    logger.info("应用关闭")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="osscout",
    description="开源项目深度尽调 Agent 平台",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册 CORS 中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 v1 版本的所有子路由，统一前缀 /api/v1
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable):
    """
    HTTP 请求日志中间件
    记录每个请求的 method、path、状态码和耗时
    """
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    logger.info(
        "请求处理完成",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    捕获所有未处理的异常，返回统一格式的错误响应
    """
    logger.error(
        "未捕获的异常",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


@app.get("/health")
async def health_check():
    """健康检查接口，用于确认服务是否正常运行"""
    return {"status": "ok"}
