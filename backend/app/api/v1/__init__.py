"""
v1 API 路由聚合

将所有 v1 版本的子路由统一注册到一个 APIRouter 下，
再在 main.py 中统一挂载到 /api/v1 前缀。

新增接口时，只需在本文件中添加一行 include_router 即可。
"""

from fastapi import APIRouter

from app.api.v1 import analyze, compare, reports, repos, tasks

# 创建 v1 版本的主路由实例
api_router = APIRouter()

# 注册各模块路由
# analyze 模块：提交分析任务
api_router.include_router(analyze.router, prefix="/analyze", tags=["分析任务"])

# tasks 模块：查询任务状态
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务状态"])

# reports 模块：获取尽调报告
api_router.include_router(reports.router, prefix="/reports", tags=["尽调报告"])

# repos 模块：仓库历史趋势
api_router.include_router(repos.router, prefix="/repos", tags=["仓库信息"])

# compare 模块：多仓库对比
api_router.include_router(compare.router, prefix="/compare", tags=["对比分析"])
