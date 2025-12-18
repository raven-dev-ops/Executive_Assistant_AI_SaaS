"""Align core table schemas with SQLAlchemy models.

This migration backfills missing columns/tables introduced after the initial
baseline migration so that SQLite CI databases created via `alembic upgrade`
match the runtime ORM models.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0003_align_core_schema"
down_revision = "0002_add_twilio_phone_number"
branch_labels = None
depends_on = None


def _table_names(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    try:
        return {idx["name"] for idx in inspector.get_indexes(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # businesses: add columns introduced after 0001 baseline.
    business_cols = _column_names(inspector, "businesses")
    business_additions: list[tuple[str, sa.Column]] = [
        (
            "api_key_last_used_at",
            sa.Column("api_key_last_used_at", sa.DateTime(), nullable=True),
        ),
        (
            "api_key_last_rotated_at",
            sa.Column("api_key_last_rotated_at", sa.DateTime(), nullable=True),
        ),
        (
            "widget_token_last_used_at",
            sa.Column("widget_token_last_used_at", sa.DateTime(), nullable=True),
        ),
        (
            "widget_token_last_rotated_at",
            sa.Column("widget_token_last_rotated_at", sa.DateTime(), nullable=True),
        ),
        (
            "widget_token_expires_at",
            sa.Column("widget_token_expires_at", sa.DateTime(), nullable=True),
        ),
        (
            "intent_threshold",
            sa.Column("intent_threshold", sa.Integer(), nullable=True),
        ),
        (
            "gcalendar_access_token",
            sa.Column("gcalendar_access_token", sa.Text(), nullable=True),
        ),
        (
            "gcalendar_refresh_token",
            sa.Column("gcalendar_refresh_token", sa.Text(), nullable=True),
        ),
        (
            "gcalendar_token_expires_at",
            sa.Column("gcalendar_token_expires_at", sa.DateTime(), nullable=True),
        ),
        (
            "gmail_access_token",
            sa.Column("gmail_access_token", sa.Text(), nullable=True),
        ),
        (
            "gmail_refresh_token",
            sa.Column("gmail_refresh_token", sa.Text(), nullable=True),
        ),
        (
            "gmail_token_expires_at",
            sa.Column("gmail_token_expires_at", sa.DateTime(), nullable=True),
        ),
        (
            "owner_email_alerts_enabled",
            sa.Column("owner_email_alerts_enabled", sa.Boolean(), nullable=True),
        ),
        ("lockdown_mode", sa.Column("lockdown_mode", sa.Boolean(), nullable=True)),
    ]
    for col_name, col in business_additions:
        if col_name not in business_cols:
            op.add_column("businesses", col)

    # users: add auth hardening fields and indexes.
    user_cols = _column_names(inspector, "users")
    if "failed_login_attempts" not in user_cols:
        op.add_column(
            "users",
            sa.Column(
                "failed_login_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if "lockout_until" not in user_cols:
        op.add_column("users", sa.Column("lockout_until", sa.DateTime(), nullable=True))
    if "reset_token_hash" not in user_cols:
        op.add_column(
            "users", sa.Column("reset_token_hash", sa.String(), nullable=True)
        )
    if "reset_token_expires_at" not in user_cols:
        op.add_column(
            "users", sa.Column("reset_token_expires_at", sa.DateTime(), nullable=True)
        )

    user_indexes = _index_names(inspector, "users")
    if (
        "reset_token_hash" in _column_names(inspector, "users")
        and "ix_users_reset_token_hash" not in user_indexes
    ):
        op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"])
    if (
        "reset_token_expires_at" in _column_names(inspector, "users")
        and "ix_users_reset_token_expires_at" not in user_indexes
    ):
        op.create_index(
            "ix_users_reset_token_expires_at", "users", ["reset_token_expires_at"]
        )

    # conversations: add intent fields.
    conversation_cols = _column_names(inspector, "conversations")
    if "intent" not in conversation_cols:
        op.add_column("conversations", sa.Column("intent", sa.String(), nullable=True))
    if "intent_confidence" not in conversation_cols:
        op.add_column(
            "conversations", sa.Column("intent_confidence", sa.Integer(), nullable=True)
        )

    # business_invites: create table used by staff invites flow.
    existing_tables = _table_names(inspector)
    if "business_invites" not in existing_tables:
        op.create_table(
            "business_invites",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("business_id", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False, server_default="staff"),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_by_user_id", sa.String(), nullable=True),
            sa.Column("created_by_user_id", sa.String(), nullable=True),
        )

    invite_indexes = _index_names(inspector, "business_invites")
    invite_index_specs: list[tuple[str, list[str]]] = [
        ("ix_business_invites_business_id", ["business_id"]),
        ("ix_business_invites_email", ["email"]),
        ("ix_business_invites_token_hash", ["token_hash"]),
        ("ix_business_invites_created_at", ["created_at"]),
        ("ix_business_invites_expires_at", ["expires_at"]),
        ("ix_business_invites_accepted_at", ["accepted_at"]),
        ("ix_business_invites_accepted_by_user_id", ["accepted_by_user_id"]),
        ("ix_business_invites_created_by_user_id", ["created_by_user_id"]),
    ]
    for index_name, columns in invite_index_specs:
        if index_name not in invite_indexes:
            op.create_index(index_name, "business_invites", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # business_invites
    if "business_invites" in _table_names(inspector):
        for index_name, _cols in [
            ("ix_business_invites_created_by_user_id", ["created_by_user_id"]),
            ("ix_business_invites_accepted_by_user_id", ["accepted_by_user_id"]),
            ("ix_business_invites_accepted_at", ["accepted_at"]),
            ("ix_business_invites_expires_at", ["expires_at"]),
            ("ix_business_invites_created_at", ["created_at"]),
            ("ix_business_invites_token_hash", ["token_hash"]),
            ("ix_business_invites_email", ["email"]),
            ("ix_business_invites_business_id", ["business_id"]),
        ]:
            if index_name in _index_names(inspector, "business_invites"):
                op.drop_index(index_name, table_name="business_invites")
        op.drop_table("business_invites")

    # conversations
    conversation_cols = _column_names(inspector, "conversations")
    if "intent_confidence" in conversation_cols:
        op.drop_column("conversations", "intent_confidence")
    if "intent" in conversation_cols:
        op.drop_column("conversations", "intent")

    # users
    user_indexes = _index_names(inspector, "users")
    if "ix_users_reset_token_expires_at" in user_indexes:
        op.drop_index("ix_users_reset_token_expires_at", table_name="users")
    if "ix_users_reset_token_hash" in user_indexes:
        op.drop_index("ix_users_reset_token_hash", table_name="users")

    user_cols = _column_names(inspector, "users")
    if "reset_token_expires_at" in user_cols:
        op.drop_column("users", "reset_token_expires_at")
    if "reset_token_hash" in user_cols:
        op.drop_column("users", "reset_token_hash")
    if "lockout_until" in user_cols:
        op.drop_column("users", "lockout_until")
    if "failed_login_attempts" in user_cols:
        op.drop_column("users", "failed_login_attempts")

    # businesses
    business_cols = _column_names(inspector, "businesses")
    for col_name in [
        "lockdown_mode",
        "owner_email_alerts_enabled",
        "gmail_token_expires_at",
        "gmail_refresh_token",
        "gmail_access_token",
        "gcalendar_token_expires_at",
        "gcalendar_refresh_token",
        "gcalendar_access_token",
        "intent_threshold",
        "widget_token_expires_at",
        "widget_token_last_rotated_at",
        "widget_token_last_used_at",
        "api_key_last_rotated_at",
        "api_key_last_used_at",
    ]:
        if col_name in business_cols:
            op.drop_column("businesses", col_name)
