"""supplier API import state; taxonomy remaps between releases

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02 13:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "import_state",
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("api_version", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_offset", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_page_skus", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("snapshot_token", sa.String(), nullable=True),
        sa.Column("page_cursor", sa.String(), nullable=True),
        sa.Column("pages", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_seen", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duplicates_dropped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("windows_reread", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("supplier_id"),
    )
    op.create_table(
        "taxonomy_remaps",
        sa.Column("old_version", sa.String(length=16), nullable=False),
        sa.Column("old_node_id", sa.Integer(), nullable=False),
        sa.Column("new_version", sa.String(length=16), nullable=False),
        sa.Column("new_node_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("old_version", "old_node_id", "new_version"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("taxonomy_remaps")
    op.drop_table("import_state")
