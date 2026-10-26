"""add invoice extraction audit fields

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2024-01-16 10:00:00.000000

Adds to invoices:
  - extraction_provider VARCHAR(50)
  - raw_extraction_json JSONB / JSON
  - extraction_confidence NUMERIC(4,3)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use JSONB for postgresql, JSON variant for others
    json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

    op.add_column("invoices", sa.Column("extraction_provider", sa.String(50), nullable=True))
    op.add_column("invoices", sa.Column("raw_extraction_json", json_type, nullable=True))
    op.add_column("invoices", sa.Column("extraction_confidence", sa.Numeric(4, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "extraction_confidence")
    op.drop_column("invoices", "raw_extraction_json")
    op.drop_column("invoices", "extraction_provider")

