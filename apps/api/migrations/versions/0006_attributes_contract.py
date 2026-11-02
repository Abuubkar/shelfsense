"""attributes, contract: validate the colour check, drop attributes_json

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02 13:20:00

Contract step of JSONB -> typed columns (docs/migrations.md). Run only after scripts/backfill_attributes.py has
finished and no running code reads or writes attributes_json; it refuses otherwise.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    missing = op.get_bind().scalar(sa.text("""
        SELECT count(*) FROM products p
        WHERE p.attributes_json <> '{}'::jsonb
          AND NOT EXISTS (SELECT 1 FROM product_attributes a WHERE a.product_id = p.id)
    """))
    if missing:
        raise RuntimeError(f"{missing} products have attributes not yet backfilled: "
                           "run scripts/backfill_attributes.py before contracting")
    # A scan, but under SHARE UPDATE EXCLUSIVE: reads and writes carry on while it checks the backfilled rows.
    op.execute("ALTER TABLE products VALIDATE CONSTRAINT products_color_base_check")
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Metadata-only: the values stay on disk until rows are rewritten, so this is quick on any table size.
    op.drop_column("products", "attributes_json")
    op.drop_table("backfill_state")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("products", sa.Column("attributes_json", postgresql.JSONB(astext_type=sa.Text()),
                                        server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_table(
        "backfill_state",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("last_id", sa.Uuid(), nullable=True),
        sa.Column("rows_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    # product_attributes holds every raw attribute, so attributes_json comes back exactly.
    op.execute("""
        UPDATE products p SET attributes_json = a.attrs
        FROM (SELECT product_id, jsonb_object_agg(name, value) AS attrs FROM product_attributes GROUP BY product_id) a
        WHERE a.product_id = p.id
    """)
    op.execute("INSERT INTO backfill_state (name, rows_done, finished_at) VALUES ('attributes', 0, now())")
