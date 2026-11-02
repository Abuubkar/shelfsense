"""workers: feeds are uploads, enrichment runs, dead letters, enrichment keyed by content hash

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02 11:00:00

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
    """Upgrade schema."""
    # A feed is now one upload: created before its bytes arrive, hashed and counted on commit. Uploading the same
    # bytes twice makes two feeds; products still only change when their content does.
    op.drop_constraint("feeds_supplier_id_file_sha256_key", "feeds", type_="unique")
    op.alter_column("feeds", "file_sha256", nullable=True)
    op.alter_column("feeds", "row_count", nullable=True)
    op.alter_column("feeds", "rejected_count", nullable=True)
    op.add_column("feeds", sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE feeds SET committed_at = created_at")

    # Existing categories were decided from the products' current content: nothing has re-imported them since.
    op.add_column("product_categories", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.execute("""
        UPDATE product_categories pc SET content_hash = p.content_hash FROM products p WHERE p.id = pc.product_id
    """)
    op.alter_column("product_categories", "content_hash", nullable=False)

    op.create_table(
        "enrichment_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("wall_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrichment_runs_product_id", "enrichment_runs", ["product_id"])
    op.create_index("ix_enrichment_runs_created_at", "enrichment_runs", ["created_at"])

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("queue", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(), nullable=False),
        sa.Column("message_body", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redriven_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("dead_letters_open_product", "dead_letters", ["queue", "product_id"], unique=True,
                    postgresql_where=sa.text("redriven_at IS NULL AND product_id IS NOT NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("dead_letters_open_product", table_name="dead_letters")
    op.drop_table("dead_letters")
    op.drop_index("ix_enrichment_runs_created_at", table_name="enrichment_runs")
    op.drop_index("ix_enrichment_runs_product_id", table_name="enrichment_runs")
    op.drop_table("enrichment_runs")
    op.drop_column("product_categories", "content_hash")

    # Uploads never committed have no hash; slice 2's schema can't hold them. If the same bytes were committed as
    # two feeds, the unique constraint below fails: merge or delete the duplicates first.
    op.execute("DELETE FROM feed_rejections WHERE feed_id IN (SELECT id FROM feeds WHERE file_sha256 IS NULL)")
    op.execute("DELETE FROM feeds WHERE file_sha256 IS NULL")
    op.drop_column("feeds", "committed_at")
    op.alter_column("feeds", "rejected_count", nullable=False)
    op.alter_column("feeds", "row_count", nullable=False)
    op.alter_column("feeds", "file_sha256", nullable=False)
    op.create_unique_constraint("feeds_supplier_id_file_sha256_key", "feeds", ["supplier_id", "file_sha256"])
