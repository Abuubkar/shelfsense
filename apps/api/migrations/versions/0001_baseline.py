"""baseline

Revision ID: 0001
Revises: 
Create Date: 2026-11-02 08:06:33.386077

"""
from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('suppliers',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('taxonomy_nodes',
    sa.Column('version', sa.String(length=16), nullable=False),
    sa.Column('node_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('full_path', sa.String(), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=False),
    sa.Column('is_leaf', sa.Boolean(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.VECTOR(dim=384), nullable=False),
    sa.ForeignKeyConstraint(['version', 'parent_id'], ['taxonomy_nodes.version', 'taxonomy_nodes.node_id'], ),
    sa.PrimaryKeyConstraint('version', 'node_id')
    )
    op.create_table('feed_rejections',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('supplier_id', sa.Uuid(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('reason_code', sa.String(length=32), nullable=False),
    sa.Column('detail', sa.String(), nullable=False),
    sa.Column('excerpt', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('file_sha256', 'row_number')
    )
    op.create_table('products',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('supplier_id', sa.Uuid(), nullable=False),
    sa.Column('supplier_sku', sa.String(length=128), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('brand', sa.String(), nullable=True),
    sa.Column('gtin', sa.String(length=14), nullable=True),
    sa.Column('price_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('attributes_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('supplier_id', 'supplier_sku')
    )
    op.create_table('product_categories',
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('taxonomy_version', sa.String(length=16), nullable=False),
    sa.Column('node_id', sa.Integer(), nullable=True),
    sa.Column('confidence', sa.Double(), nullable=False),
    sa.Column('candidate_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('prompt_version', sa.String(), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('total_ms', sa.Integer(), nullable=False),
    sa.Column('prompt_eval_ms', sa.Integer(), nullable=False),
    sa.Column('eval_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['taxonomy_version', 'node_id'], ['taxonomy_nodes.version', 'taxonomy_nodes.node_id'], ),
    sa.PrimaryKeyConstraint('product_id', 'taxonomy_version')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('product_categories')
    op.drop_table('products')
    op.drop_table('feed_rejections')
    op.drop_table('taxonomy_nodes')
    op.drop_table('suppliers')
    op.execute("DROP EXTENSION IF EXISTS vector")
