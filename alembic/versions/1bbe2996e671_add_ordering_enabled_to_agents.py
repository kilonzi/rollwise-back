"""add_ordering_enabled_to_agents

Revision ID: 1bbe2996e671
Revises: 04106b945043
Create Date: 2025-09-26 21:21:41.314146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bbe2996e671'
down_revision: Union[str, Sequence[str], None] = '04106b945043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agents', sa.Column('ordering_enabled', sa.Boolean(), nullable=True, default=True))
    # Update existing agents to have ordering_enabled=True by default
    op.execute("UPDATE agents SET ordering_enabled = true WHERE ordering_enabled IS NULL")
    # Make the column NOT NULL after updating existing records
    op.alter_column('agents', 'ordering_enabled', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agents', 'ordering_enabled')
