"""One-shot script to correct issue #252 and link PR #302.

Updates tracked_issues record: status -> 'in_review', pr_number -> 302
Creates TrackedPR record: pr_number=302, status='open' (if not exists)

Usage:
    poetry run python scripts/fix_issue_252.py           # apply changes
    poetry run python scripts/fix_issue_252.py --dry-run # preview only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project src is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select

from claudedev.config import load_settings
from claudedev.core.state import (
    IssueStatus,
    PRStatus,
    TrackedIssue,
    TrackedPR,
    close_db,
    get_session,
    init_db,
)


async def fix_issue_252(*, dry_run: bool) -> None:
    settings = load_settings()
    print(f"Connecting to: {settings.db_url.split('@')[-1]}")
    await init_db(settings.db_url)

    try:
        async with get_session() as session:
            # --- locate the tracked issue ---
            result = await session.execute(
                select(TrackedIssue).where(TrackedIssue.github_issue_number == 252)
            )
            issue = result.scalar_one_or_none()

            if issue is None:
                print("ERROR: No TrackedIssue found with github_issue_number=252")
                return

            print(
                f"Found TrackedIssue id={issue.id}  repo_id={issue.repo_id}  "
                f"status={issue.status!r}  pr_number={issue.pr_number}"
            )

            old_status = issue.status
            old_pr = issue.pr_number

            # --- update the issue record ---
            issue.status = IssueStatus.IN_REVIEW
            issue.pr_number = 302

            # --- upsert TrackedPR ---
            pr_result = await session.execute(
                select(TrackedPR).where(
                    TrackedPR.pr_number == 302,
                    TrackedPR.repo_id == issue.repo_id,
                )
            )
            existing_pr = pr_result.scalar_one_or_none()

            if existing_pr is None:
                new_pr = TrackedPR(
                    issue_id=issue.id,
                    repo_id=issue.repo_id,
                    pr_number=302,
                    status=PRStatus.OPEN,
                )
                session.add(new_pr)
                pr_action = "Will create TrackedPR(pr_number=302, status='open')"
            else:
                pr_action = (
                    f"TrackedPR #302 already exists (id={existing_pr.id}, "
                    f"status={existing_pr.status!r})"
                )
                if existing_pr.issue_id != issue.id:
                    existing_pr.issue_id = issue.id
                    pr_action += " — updated issue_id link"

            print()
            print("Planned changes:")
            print(
                f"  tracked_issues id={issue.id}: "
                f"status {old_status!r} -> 'in_review', "
                f"pr_number {old_pr} -> 302"
            )
            print(f"  {pr_action}")

            if dry_run:
                print()
                print("[DRY RUN] — rolling back, no changes written")
                await session.rollback()
            else:
                await session.commit()
                print()
                print("Changes committed successfully.")

    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix tracked_issues #252: link PR #302 and set status to in_review"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to the database",
    )
    args = parser.parse_args()
    asyncio.run(fix_issue_252(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
