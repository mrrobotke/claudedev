#!/usr/bin/env python3
"""Migrate ClaudeDev data from SQLite to PostgreSQL.

Usage: python scripts/migrate_sqlite_to_pg.py
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

SQLITE_URL = f"sqlite+aiosqlite:///{Path.home() / '.claudedev' / 'claudedev.db'}"
PG_URL = "postgresql+asyncpg://iworldafric@localhost/claudedev"

# Insert order respects FK constraints (agent_sessions.issue_id deferred)
TABLES_IN_ORDER = ["projects", "repos", "agent_sessions", "tracked_issues", "tracked_prs"]

# Datetime columns that need conversion from SQLite string to Python datetime.
# JSON columns are left as strings — PG json type accepts JSON strings directly.
DATETIME_COLUMNS: dict[str, set[str]] = {
    "projects": {"created_at"},
    "tracked_issues": {"enhanced_at", "implementation_started_at", "created_at"},
    "tracked_prs": {"created_at"},
    "agent_sessions": {"started_at", "ended_at"},
}

DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
]


def parse_datetime(val: str) -> datetime:
    """Parse a datetime string trying multiple formats."""
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    msg = f"Cannot parse datetime: {val!r}"
    raise ValueError(msg)


def convert_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Convert SQLite string values to proper Python types for asyncpg.

    - Datetime columns: string -> datetime object
    - JSON columns: left as strings (PG json type accepts JSON strings)
    """
    result = dict(row)

    for col in DATETIME_COLUMNS.get(table_name, set()):
        val = result.get(col)
        if isinstance(val, str):
            result[col] = parse_datetime(val)

    return result


async def read_all_rows(engine: Any, table_name: str) -> list[dict[str, Any]]:
    """Read all rows from a table as list of dicts."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT * FROM {table_name}"))
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]


async def get_row_count(engine: Any, table_name: str) -> int:
    """Get the number of rows in a table."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar_one()


async def create_schema() -> None:
    """Create PG tables using ORM metadata, then dispose the engine.

    This runs in isolation so the ORM type adapters don't interfere
    with the raw text() inserts in the migration.
    """
    schema_engine = create_async_engine(PG_URL, echo=False)
    from claudedev.core.state import Base

    async with schema_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await schema_engine.dispose()
    print("Schema created/verified in PostgreSQL")


async def migrate() -> None:
    """Run the SQLite to PostgreSQL migration."""
    # Step 1: Create schema with a separate engine
    await create_schema()

    # Step 2: Create fresh engines for data transfer (no ORM type adapters)
    src = create_async_engine(SQLITE_URL, echo=False, connect_args={"timeout": 30})
    dst = create_async_engine(PG_URL, echo=False)

    print("\n=== Pre-migration SQLite row counts ===")
    src_counts: dict[str, int] = {}
    for table in TABLES_IN_ORDER:
        count = await get_row_count(src, table)
        src_counts[table] = count
        print(f"  {table}: {count}")

    # Read all data from SQLite
    data: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES_IN_ORDER:
        data[table] = await read_all_rows(src, table)

    # Store agent_sessions.issue_id mapping for deferred update
    session_issue_map: dict[int, int] = {}
    for row in data["agent_sessions"]:
        if row.get("issue_id") is not None:
            session_issue_map[row["id"]] = row["issue_id"]

    # Insert into PostgreSQL in a single transaction
    async with dst.begin() as conn:
        # Truncate tables in reverse order to handle FK constraints
        for table in reversed(TABLES_IN_ORDER):
            await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

        for table in TABLES_IN_ORDER:
            rows = data[table]
            if not rows:
                print(f"  {table}: 0 rows (skipped)")
                continue

            for row in rows:
                insert_row = convert_row(table, row)

                # For agent_sessions, NULL out issue_id on first pass
                # (tracked_issues not yet inserted)
                if table == "agent_sessions":
                    insert_row["issue_id"] = None

                cols = list(insert_row.keys())
                col_str = ", ".join(cols)
                placeholders = ", ".join(f":{c}" for c in cols)
                await conn.execute(
                    text(f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"),
                    insert_row,
                )

            print(f"  {table}: {len(rows)} rows inserted")

        # Deferred update: set agent_sessions.issue_id
        for session_id, issue_id in session_issue_map.items():
            await conn.execute(
                text("UPDATE agent_sessions SET issue_id = :issue_id WHERE id = :id"),
                {"issue_id": issue_id, "id": session_id},
            )
        if session_issue_map:
            print(f"  agent_sessions.issue_id: {len(session_issue_map)} rows updated")

        # Reset sequences for tables that have data
        for table in TABLES_IN_ORDER:
            if not data[table]:
                continue
            await conn.execute(
                text(
                    f"SELECT setval("
                    f"pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT MAX(id) FROM {table}))"
                )
            )
        print("  Sequences reset")

    print("\n=== Post-migration PostgreSQL row counts ===")
    all_match = True
    for table in TABLES_IN_ORDER:
        count = await get_row_count(dst, table)
        match = count == src_counts[table]
        status = "OK" if match else "MISMATCH"
        if not match:
            all_match = False
        print(f"  {table}: {count} {status}")

    await src.dispose()
    await dst.dispose()

    if all_match:
        print("\nMigration complete! All row counts match.")
    else:
        print("\nMigration completed with MISMATCHES. Please investigate.")


if __name__ == "__main__":
    asyncio.run(migrate())
