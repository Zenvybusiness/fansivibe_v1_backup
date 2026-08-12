"""Add the frozen error body to analysis_runs (failed runs, TRX-5).

The contract (`HAIRSTYLE_RECOMMENDATION_API.md` §4.2/§7) requires a failed
run to carry ``status='failed'`` + a frozen ``error`` body
(``error.code = PROCESSING_FAILURE``, ``details.run_id``) instead of leaving
the run stuck in ``pending``. This adds the nullable JSONB ``error`` column
and the guarded ``fail_analysis_run`` function — the only failure-path
``analysis_runs`` mutation, write-once like ``complete_analysis_run``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _fail_function() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION fail_analysis_run(
                p_run_id uuid,
                p_user_id uuid,
                p_error jsonb
            ) RETURNS boolean AS $$
            DECLARE
                updated_count integer;
            BEGIN
                UPDATE analysis_runs
                   SET status = 'failed',
                       error = p_error,
                       completed_at = now()
                 WHERE id = p_run_id
                   AND user_id = p_user_id
                   AND status = 'pending';
                GET DIAGNOSTICS updated_count = ROW_COUNT;
                RETURN updated_count = 1;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("error", JSONB(), nullable=True),
    )
    _fail_function()


def downgrade() -> None:
    op.execute(sa.text("DROP FUNCTION IF EXISTS fail_analysis_run(uuid, uuid, jsonb)"))
    op.drop_column("analysis_runs", "error")
