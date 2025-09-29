"""rename_agent_memory_table_to_memories

Revision ID: 21a1b639b7a3
Revises: 25d28d3af0c9
Create Date: 2025-09-27 04:07:28.658329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21a1b639b7a3'
down_revision: Union[str, Sequence[str], None] = '25d28d3af0c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename agent_memory table to memories."""
    op.rename_table('agent_memory', 'memories')


def downgrade() -> None:
    """Rename memories table back to agent_memory."""
    op.rename_table('memories', 'agent_memory')
