"""
初始迁移：创建核心数据表

创建 repositories、analysis_tasks、due_diligence_reports、metric_history 四张表
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 修订标识符
revision: str = "001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建所有表"""
    # 创建 repositories 表
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("repo", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_language", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("star_count", sa.Integer(), nullable=True),
        sa.Column("fork_count", sa.Integer(), nullable=True),
        sa.Column("open_issue_count", sa.Integer(), nullable=True),
        sa.Column("license", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # 创建 analysis_tasks 表
    op.create_table(
        "analysis_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="taskstatus"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 创建 due_diligence_reports 表
    op.create_table(
        "due_diligence_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("overall_rating", sa.String(length=5), nullable=True),
        sa.Column("community_score", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("security_score", sa.Integer(), nullable=True),
        sa.Column("evolution_score", sa.Integer(), nullable=True),
        sa.Column("key_findings", sa.JSON(), nullable=True),
        sa.Column("recommendations", sa.JSON(), nullable=True),
        sa.Column("raw_results", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repositories.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["analysis_tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 创建 metric_history 表
    op.create_table(
        "metric_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=100), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """降级：删除所有表"""
    op.drop_table("metric_history")
    op.drop_table("due_diligence_reports")
    op.drop_table("analysis_tasks")
    op.drop_table("repositories")
