"""Add tenant time_zone and Google Calendar watch/sync state fields."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0006_add_business_timezone_and_gcalendar_watch_fields"
down_revision = "0005_add_feedback_entries_table"
branch_labels = None
depends_on = None


def _table_names(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "businesses" not in _table_names(inspector):
        return

    business_cols = _column_names(inspector, "businesses")
    additions: list[tuple[str, sa.Column]] = [
        ("time_zone", sa.Column("time_zone", sa.String(length=64), nullable=True)),
        (
            "gcalendar_channel_id",
            sa.Column("gcalendar_channel_id", sa.String(length=255), nullable=True),
        ),
        (
            "gcalendar_channel_token",
            sa.Column("gcalendar_channel_token", sa.String(length=255), nullable=True),
        ),
        (
            "gcalendar_resource_id",
            sa.Column("gcalendar_resource_id", sa.String(length=255), nullable=True),
        ),
        (
            "gcalendar_channel_expires_at",
            sa.Column("gcalendar_channel_expires_at", sa.DateTime(), nullable=True),
        ),
        (
            "gcalendar_sync_token",
            sa.Column("gcalendar_sync_token", sa.Text(), nullable=True),
        ),
        (
            "gcalendar_last_sync_at",
            sa.Column("gcalendar_last_sync_at", sa.DateTime(), nullable=True),
        ),
    ]
    for col_name, col in additions:
        if col_name not in business_cols:
            op.add_column("businesses", col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "businesses" not in _table_names(inspector):
        return

    business_cols = _column_names(inspector, "businesses")
    for col_name in [
        "gcalendar_last_sync_at",
        "gcalendar_sync_token",
        "gcalendar_channel_expires_at",
        "gcalendar_resource_id",
        "gcalendar_channel_token",
        "gcalendar_channel_id",
        "time_zone",
    ]:
        if col_name in business_cols:
            op.drop_column("businesses", col_name)
