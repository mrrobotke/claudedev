"""add worktree_path and claude_session_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-12 00:53:11.253327

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add v0.2.0 Phase 2 columns for worktree tracking and session binding."""
    # Use raw SQL with IF NOT EXISTS for idempotent migration on existing DBs.
    op.execute("ALTER TABLE tracked_issues ADD COLUMN IF NOT EXISTS worktree_path VARCHAR(500)")
    op.execute("ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS claude_session_id VARCHAR(255)")


def downgrade() -> None:
    """Remove v0.2.0 Phase 2 columns."""
    op.drop_column("agent_sessions", "claude_session_id")
    op.drop_column("tracked_issues", "worktree_path")
