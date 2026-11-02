"""attributes, expand: typed facet columns and product_attributes beside attributes_json

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02 13:10:00

Expand step of JSONB -> typed columns (docs/migrations.md). Only adds: code that reads attributes_json keeps
working. Every statement is metadata-only (nullable columns without defaults, new tables, a NOT VALID check), so
the brief ACCESS EXCLUSIVE lock on products is taken and released at once. lock_timeout makes the migration fail
fast instead of queueing behind a long transaction while blocking every query behind it.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BASE_COLORS = ("black", "white", "gray", "brown", "beige", "red", "pink", "orange", "yellow", "green", "blue", "navy",
               "purple", "gold", "silver", "multicolor")  # normalize.BASE_COLORS when this was written


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("products", sa.Column("color_base", sa.String(length=16), nullable=True))
    op.add_column("products", sa.Column("material", sa.String(length=64), nullable=True))
    op.add_column("products", sa.Column("gender", sa.String(length=16), nullable=True))
    op.add_column("products", sa.Column("size_system", sa.String(length=8), nullable=True))
    op.add_column("products", sa.Column("size_value", sa.String(length=16), nullable=True))
    # Enforced for every write from now on; existing rows are checked by VALIDATE in the contract step.
    colors = ", ".join(f"'{c}'" for c in BASE_COLORS)
    op.execute(f"ALTER TABLE products ADD CONSTRAINT products_color_base_check "
               f"CHECK (color_base IN ({colors})) NOT VALID")
    op.create_table(
        "product_attributes",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "name"),
    )
    # Where scripts/backfill_attributes.py got to, so a stopped backfill resumes. Dropped by the contract step.
    op.create_table(
        "backfill_state",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("last_id", sa.Uuid(), nullable=True),
        sa.Column("rows_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Code past the expand step writes attributes only to product_attributes: copy them back first, so the old
    # code sees every product's attributes.
    op.execute("""
        UPDATE products p SET attributes_json = a.attrs
        FROM (SELECT product_id, jsonb_object_agg(name, value) AS attrs FROM product_attributes GROUP BY product_id) a
        WHERE a.product_id = p.id AND p.attributes_json IS DISTINCT FROM a.attrs
    """)
    op.drop_table("backfill_state")
    op.drop_table("product_attributes")
    op.execute("ALTER TABLE products DROP CONSTRAINT products_color_base_check")
    for column in ("size_value", "size_system", "gender", "material", "color_base"):
        op.drop_column("products", column)
