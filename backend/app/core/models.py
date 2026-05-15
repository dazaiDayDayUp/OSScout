"""
数据库模型定义
对应 PROJECT_PLAN.md 中的核心实体设计
"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有模型的基类"""


class TaskStatus(PyEnum):
    """分析任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Repository(Base):
    """GitHub 仓库基础信息表"""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    repo: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    star_count: Mapped[int] = mapped_column(Integer, default=0)
    fork_count: Mapped[int] = mapped_column(Integer, default=0)
    open_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    license: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 关联关系
    tasks: Mapped[list["AnalysisTask"]] = relationship(
        "AnalysisTask", back_populates="repository"
    )
    reports: Mapped[list["DueDiligenceReport"]] = relationship(
        "DueDiligenceReport", back_populates="repository"
    )
    metric_history: Mapped[list["MetricHistory"]] = relationship(
        "MetricHistory", back_populates="repository"
    )


class AnalysisTask(Base):
    """分析任务表"""

    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id"), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关联关系
    repository: Mapped["Repository"] = relationship("Repository", back_populates="tasks")
    report: Mapped["DueDiligenceReport | None"] = relationship(
        "DueDiligenceReport", back_populates="task", uselist=False
    )


class DueDiligenceReport(Base):
    """尽调报告表"""

    __tablename__ = "due_diligence_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_tasks.id"), nullable=False
    )
    repo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id"), nullable=False
    )
    overall_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    overall_rating: Mapped[str] = mapped_column(String(5), default="D")  # A+/A/B+/B/C/D
    community_score: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    security_score: Mapped[int] = mapped_column(Integer, default=0)
    evolution_score: Mapped[int] = mapped_column(Integer, default=0)
    key_findings: Mapped[list[dict]] = mapped_column(JSON, default=list)  # 关键发现列表
    recommendations: Mapped[list[str]] = mapped_column(JSON, default=list)  # 建议列表
    raw_results: Mapped[dict] = mapped_column(JSON, default=dict)  # 各 Agent 原始输出
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关联关系
    task: Mapped["AnalysisTask"] = relationship("AnalysisTask", back_populates="report")
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="reports"
    )


class MetricHistory(Base):
    """指标历史表，用于趋势分析"""

    __tablename__ = "metric_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 例如 "bus_factor"
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关联关系
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="metric_history"
    )
