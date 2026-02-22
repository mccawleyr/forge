"""Add conversation AI models

Revision ID: 001_conversation
Revises: None
Create Date: 2025-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_conversation'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_message_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('context', sa.Text()),
    )
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_last_message_at', 'conversations', ['last_message_at'])

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('direction', sa.String(10)),
        sa.Column('content', sa.Text()),
        sa.Column('ai_intent', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])

    # Create recipes table
    op.create_table(
        'recipes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('ingredients', sa.Text()),
        sa.Column('instructions', sa.Text()),
        sa.Column('servings', sa.Integer(), default=1),
        sa.Column('calories_per_serving', sa.Integer()),
        sa.Column('protein_g', sa.Numeric(5, 1)),
        sa.Column('carbs_g', sa.Numeric(5, 1)),
        sa.Column('fat_g', sa.Numeric(5, 1)),
        sa.Column('source', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_recipes_user_id', 'recipes', ['user_id'])

    # Create meal_plans table
    op.create_table(
        'meal_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('plan_data', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_meal_plans_user_id', 'meal_plans', ['user_id'])
    op.create_index('ix_meal_plans_week_start', 'meal_plans', ['week_start'])

    # Create grocery_lists table
    op.create_table(
        'grocery_lists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(100)),
        sa.Column('items', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime()),
    )
    op.create_index('ix_grocery_lists_user_id', 'grocery_lists', ['user_id'])

    # Create reminders table
    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reminder_type', sa.String(30)),
        sa.Column('schedule', sa.String(50)),
        sa.Column('message_template', sa.Text()),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('last_sent_at', sa.DateTime()),
    )
    op.create_index('ix_reminders_user_id', 'reminders', ['user_id'])
    op.create_index('ix_reminders_enabled', 'reminders', ['enabled'])


def downgrade() -> None:
    op.drop_table('reminders')
    op.drop_table('grocery_lists')
    op.drop_table('meal_plans')
    op.drop_table('recipes')
    op.drop_table('messages')
    op.drop_table('conversations')
