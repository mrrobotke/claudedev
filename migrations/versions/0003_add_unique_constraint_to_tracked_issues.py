"""Add unique constraint to tracked_issues (repo_id, github_issue_number).

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Remove duplicate rows, keeping the one with the highest id
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM tracked_issues
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM tracked_issues
                GROUP BY repo_id, github_issue_number
            )
        """)
    )
    # Step 2: Add unique constraint
    op.create_unique_constraint(
        "uq_tracked_issues_repo_issue",
        "tracked_issues",
        ["repo_id", "github_issue_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_tracked_issues_repo_issue", "tracked_issues", type_="unique")
