"""add_calendar_fields_to_agents

Revision ID: 8128277ae218
Revises: dda05670396c
Create Date: 2025-09-15 22:58:02.081882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8128277ae218'
down_revision: Union[str, Sequence[str], None] = 'dda05670396c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add calendar integration fields to agents table
    op.add_column('agents', sa.Column('calendar_id', sa.String(), nullable=True))
    op.add_column('agents', sa.Column('business_hours', sa.JSON(), nullable=True))
    op.add_column('agents', sa.Column('default_slot_duration', sa.Integer(), nullable=True, default=30))
    op.add_column('agents', sa.Column('max_daily_appointments', sa.Integer(), nullable=True, default=8))
    op.add_column('agents', sa.Column('buffer_time', sa.Integer(), nullable=True, default=15))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove calendar integration fields from agents table
    op.drop_column('agents', 'buffer_time')
    op.drop_column('agents', 'max_daily_appointments')
    op.drop_column('agents', 'default_slot_duration')
    op.drop_column('agents', 'business_hours')
    op.drop_column('agents', 'calendar_id')
