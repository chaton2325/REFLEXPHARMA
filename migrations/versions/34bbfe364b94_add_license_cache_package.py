"""add license_cache.package

Revision ID: 34bbfe364b94
Revises: 5d4221da5df3
Create Date: 2026-07-25 01:39:40.778936

Fichier réécrit à la main : l'autogénération mélangeait ce changement avec le
bruit habituel de dérive entre le schéma historique (self-heal ALTER TABLE dans
app.py/run.py) et les modèles actuels (voir la migration baseline 5d4221da5df3
pour le même constat). On ne garde ici que le vrai changement.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '34bbfe364b94'
down_revision = '5d4221da5df3'
branch_labels = None
depends_on = None


def upgrade():
    # server_default requis : des lignes license_cache existent déjà (tests
    # précédents), une colonne NOT NULL sans défaut échouerait dessus.
    with op.batch_alter_table('license_cache', schema=None) as batch_op:
        batch_op.add_column(sa.Column('package', sa.String(length=20), nullable=False, server_default='offline'))


def downgrade():
    with op.batch_alter_table('license_cache', schema=None) as batch_op:
        batch_op.drop_column('package')
