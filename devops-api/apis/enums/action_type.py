from enum import Enum

'''
加完action_type之後, 要在ablemic中migrate中手動建立一個新的action_type出來, 
然後進行升版

 """add_activity_enum_modify_hook

Revision ID: daaf84c340cd
Revises: 1f0e2963b684
Create Date: 2022-01-07 14:29:18.562814

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'daaf84c340cd'
down_revision = '1f0e2963b684'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'NEW_ACTION_TYPE_NAME'")


def downgrade():
    # We won't put things back
    pass

'''


class ActionType(Enum):
    CREATE_PROJECT = 1  # Must return a dict with key "project_id"
    UPDATE_PROJECT = 2  # Requires argument "project_id"
    DELETE_PROJECT = 3  # Requires argument "project_id"
    ADD_MEMBER = 4  # Requires argument "project_id" and "user_id"
    REMOVE_MEMBER = 5  # Requires argument "project_id" and "user_id"
    CREATE_USER = 6  # Must return a dict with key "user_id"
    UPDATE_USER = 7  # Requires argument "user_id"
    DELETE_USER = 8  # Requires argument "user_id"
    DELETE_ISSUE = 9  # Requires argument "issue_id"
    # ADD_TAG = 10  # Requires argument "project_id"
    # DELETE_TAG = 11  # Requires argument "project_id"
    MODIFY_HOOK = 12  # Requires argument "issue_id"
    RECREATE_PROJECT = 13  # Requires argument "project_id"
    ENABLE_ISSUE_CHECK = 14  # Requires argument "project_id"
    DISABLE_ISSUE_CHECK = 15  # Requires argument "project_id"
    ENABLE_PLUGIN = 16  # Required user_id
    DISABLE_PLUGIN = 17  # Required user_id
    DELETE_SIDEEX_JSONFILE = 18
    DELETE_EXCALIDRAW = 19
    RESTORE_EXCALIDRAW_HISTORY = 20
    CREATE_SC = 21
    DELETE_SC = 22
    ENABLED_SC = 23
    DISABLED_SC = 24
