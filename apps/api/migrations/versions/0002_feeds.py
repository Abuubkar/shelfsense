"""feeds: one row per imported file; rejections point at it

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02 10:30:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "feeds",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", "file_sha256"),
    )
    op.add_column("feed_rejections", sa.Column("feed_id", sa.Uuid(), nullable=True))
    # Files imported before this migration: one feed per (supplier, file hash). Their row counts weren't stored,
    # so row_count is the highest rejected row number minus the header, a lower bound.
    op.execute("""
        INSERT INTO feeds (supplier_id, file_name, file_sha256, row_count, rejected_count, created_at)
        SELECT supplier_id, min(file_name), file_sha256, max(row_number) - 1, count(*), min(created_at)
        FROM feed_rejections GROUP BY supplier_id, file_sha256
    """)
    op.execute("""
        UPDATE feed_rejections r SET feed_id = f.id
        FROM feeds f WHERE f.supplier_id = r.supplier_id AND f.file_sha256 = r.file_sha256
    """)
    op.alter_column("feed_rejections", "feed_id", nullable=False)
    op.create_foreign_key("feed_rejections_feed_id_fkey", "feed_rejections", "feeds", ["feed_id"], ["id"])
    op.create_unique_constraint("feed_rejections_feed_id_row_number_key", "feed_rejections", ["feed_id", "row_number"])
    op.drop_constraint("feed_rejections_file_sha256_row_number_key", "feed_rejections", type_="unique")
    op.drop_constraint("feed_rejections_supplier_id_fkey", "feed_rejections", type_="foreignkey")
    op.drop_column("feed_rejections", "supplier_id")
    op.drop_column("feed_rejections", "file_name")
    op.drop_column("feed_rejections", "file_sha256")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("feed_rejections", sa.Column("supplier_id", sa.Uuid(), nullable=True))
    op.add_column("feed_rejections", sa.Column("file_name", sa.String(), nullable=True))
    op.add_column("feed_rejections", sa.Column("file_sha256", sa.String(length=64), nullable=True))
    op.execute("""
        UPDATE feed_rejections r SET supplier_id = f.supplier_id, file_name = f.file_name, file_sha256 = f.file_sha256
        FROM feeds f WHERE f.id = r.feed_id
    """)
    for column in ("supplier_id", "file_name", "file_sha256"):
        op.alter_column("feed_rejections", column, nullable=False)
    op.create_foreign_key("feed_rejections_supplier_id_fkey", "feed_rejections", "suppliers", ["supplier_id"], ["id"])
    op.create_unique_constraint("feed_rejections_file_sha256_row_number_key", "feed_rejections", ["file_sha256", "row_number"])
    op.drop_constraint("feed_rejections_feed_id_row_number_key", "feed_rejections", type_="unique")
    op.drop_constraint("feed_rejections_feed_id_fkey", "feed_rejections", type_="foreignkey")
    op.drop_column("feed_rejections", "feed_id")
    op.drop_table("feeds")
