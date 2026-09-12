"""D-AUTH-1 credential + session store (real authentication).

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-12

Real multi-user authentication (P0 gate D-AUTH-1):

- `users.password_hash TEXT NULL` — bcrypt hash of the account password
  (never the password itself). NULL for legacy dev rows and
  non-password identities. Email accounts use provider "email" with the
  normalized email as subject, so email uniqueness stays enforced by
  the existing `uq_users_auth_pair` pair constraint (BC-1) — no new
  unique constraint invented.
- `users.register_idempotency_key TEXT NULL` — the C-12 replay key of
  the `POST /v1/auth/register` that created the account: same key +
  same payload replays to the same account (never a duplicate);
  same email + different key is a 409 duplicate (M7 replay/conflict
  semantics for account creation).
- `user_sessions` — the R51 session/token store instantiation: one row
  per device/session, `jti` of the JWT. `token_digest` (SHA-256 of the
  JWT, UNIQUE) identifies the row without persisting the bearer token.
  `revoked_at` stamps logout; `user_id -> users CASCADE` so every
  session dies with the account (TRX-8). Index `(user_id, expires_at)`
  for per-user session scans.

No backfill (credentials/sessions accrue prospectively); legacy rows
keep NULL credential columns and stay valid. Fully reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TEXT

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", TEXT, nullable=True))
    op.add_column(
        "users", sa.Column("register_idempotency_key", TEXT, nullable=True)
    )
    op.create_table(
        "user_sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", TEXT, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "token_digest", name="uq_user_sessions_token_digest"
        ),
    )
    op.create_index(
        "ix_user_sessions_user_id_expires_at",
        "user_sessions",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_sessions_user_id_expires_at", table_name="user_sessions"
    )
    op.drop_table("user_sessions")
    op.drop_column("users", "register_idempotency_key")
    op.drop_column("users", "password_hash")
