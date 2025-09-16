"""add_blocked_dates_field_to_agents

Revision ID: 352ef9652323
Revises: 8128277ae218
Create Date: 2025-09-15 23:35:53.322463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '352ef9652323'
down_revision: Union[str, Sequence[str], None] = '8128277ae218'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add blocked_dates field to agents table
    op.add_column('agents', sa.Column('blocked_dates', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove blocked_dates field from agents table
    op.drop_column('agents', 'blocked_dates')
