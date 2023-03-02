"""update excalidraw table

Revision ID: aac2d1158a8c
Revises: 57977cc66b66
Create Date: 2022-12-01 12:17:13.426727

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aac2d1158a8c'
down_revision = '57977cc66b66'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('excalidraw', sa.Column('file_key', sa.String(), nullable=True))
    op.add_column('excalidraw_json', sa.Column('file_value', sa.JSON(), nullable=True))
    op.drop_column('excalidraw_json', 'json_key')
    op.alter_column('pict', 'project_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('pict', 'project_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.add_column('excalidraw_json', sa.Column('json_key', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_column('excalidraw_json', 'file_value')
    op.drop_column('excalidraw', 'file_key')
    # ### end Alembic commands ###