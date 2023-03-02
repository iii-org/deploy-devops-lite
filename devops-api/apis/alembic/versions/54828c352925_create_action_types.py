"""CREATE_ACTION_TYPES

Revision ID: 54828c352925
Revises: 4861747b578a
Create Date: 2023-01-19 11:16:34.099641

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "54828c352925"
down_revision = "4861747b578a"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'CREATE_SC'")
        op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'DELETE_SC'")


def downgrade():
    pass
