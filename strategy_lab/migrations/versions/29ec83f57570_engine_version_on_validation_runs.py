"""engine version on validation runs

Revision ID: 29ec83f57570
Revises: dd6ec1eb455b
Create Date: 2026-09-13 19:10:14.408041+00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '29ec83f57570'
down_revision = 'dd6ec1eb455b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Колонка добавляется с умолчанием, существующие прогоны помечаются
    # версией движка до исправления знака эффекта, затем умолчание снимается.
    op.add_column("validation_runs",
                  sa.Column("engine_version", sa.String(length=48), nullable=False,
                            server_default="v0.1_pre_direction_fix"))
    op.alter_column("validation_runs", "engine_version", server_default=None)


def downgrade() -> None:
    op.drop_column("validation_runs", "engine_version")
