"""
Add notify_email column to analysis_tasks table

Revision ID: 002
Revises: 001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add notify_email column and index to analysis_tasks"""
    op.add_column(
        "analysis_tasks",
        sa.Column("notify_email", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_analysis_tasks_notify_email",
        "analysis_tasks",
        ["notify_email"],
        unique=False,
    )


def downgrade() -> None:
    """Remove notify_email column and index"""
    op.drop_index("ix_analysis_tasks_notify_email", table_name="analysis_tasks")
    op.drop_column("analysis_tasks", "notify_email")
