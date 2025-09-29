"""add_phone_number_to_events_table

Revision ID: 04106b945043
Revises: d61e683a0f2a
Create Date: 2025-09-26 20:00:16.737783

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04106b945043'
down_revision: Union[str, Sequence[str], None] = 'd61e683a0f2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('events', sa.Column('phone_number', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('events', 'phone_number')
