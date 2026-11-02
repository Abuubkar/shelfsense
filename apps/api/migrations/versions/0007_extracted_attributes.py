"""extracted attributes with evidence; grounding counts on enrichment runs

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02 20:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "product_extracted_attributes",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("unit", sa.String(length=8), nullable=True),
        sa.Column("evidence_field", sa.String(length=16), nullable=False),
        sa.Column("evidence_start", sa.Integer(), nullable=False),
        sa.Column("evidence_end", sa.Integer(), nullable=False),
        sa.Column("evidence_text", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "name"),
    )
    # Nullable without a default: metadata-only on a big table.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("enrichment_runs", sa.Column("ungrounded_attributes", sa.Integer(), nullable=True))
    op.add_column("enrichment_runs", sa.Column("unnormalized_attributes", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column("enrichment_runs", "unnormalized_attributes")
    op.drop_column("enrichment_runs", "ungrounded_attributes")
    op.drop_table("product_extracted_attributes")
