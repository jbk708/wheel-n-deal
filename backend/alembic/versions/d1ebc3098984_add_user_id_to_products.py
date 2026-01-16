"""Add user_id to products

Revision ID: d1ebc3098984
Revises: aa357c425f66
Create Date: 2026-01-16 12:58:19.404034

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1ebc3098984"
down_revision: Union[str, Sequence[str], None] = "aa357c425f66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds user_id FK to products and changes unique constraint from url alone
    to (user_id, url) composite - allowing multiple users to track the same URL.

    Note: Any existing products without a user will be deleted. This is acceptable
    for development; production would need a data migration strategy.
    """
    # Delete any orphaned products (no user to assign them to)
    op.execute("DELETE FROM price_history WHERE product_id IN (SELECT id FROM products)")
    op.execute("DELETE FROM products")

    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False))
        batch_op.drop_index("ix_products_url")
        batch_op.create_index("ix_products_url", ["url"], unique=False)
        batch_op.create_index("ix_products_user_id", ["user_id"], unique=False)
        batch_op.create_unique_constraint("uq_user_product_url", ["user_id", "url"])
        batch_op.create_foreign_key("fk_products_user_id", "users", ["user_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_constraint("fk_products_user_id", type_="foreignkey")
        batch_op.drop_constraint("uq_user_product_url", type_="unique")
        batch_op.drop_index("ix_products_user_id")
        batch_op.drop_index("ix_products_url")
        batch_op.create_index("ix_products_url", ["url"], unique=True)
        batch_op.drop_column("user_id")
