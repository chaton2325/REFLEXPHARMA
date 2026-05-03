import os
from flask import Flask, redirect, url_for
from extensions import db, login_manager, migrate
from flask_migrate import upgrade
from sqlalchemy import text

# Importation de TOUS les modèles pour que SQLAlchemy les connaisse
from models.user import User
from models.poste import Poste
from models.permission import Permission
from models.fournisseur import Fournisseur
from models.groupe_fournisseur import GroupeFournisseur
from models.rayon import Rayon
from models.famille import Famille
from models.section import Section
from models.produit import Produit
from models.stock import Stock
from models.stock_modification import StockModification
from models.stock_reason import StockReason
from models.stock_exit_log import StockExitLog
from models.groupe_client import GroupeClient
from models.client import Client
from models.client_modification_log import ClientModificationLog
from models.vente import Vente, VenteLigne

from config import config

def ensure_database_schema(app):
    with app.app_context():
        db.create_all()

        columns_to_check = {
            'ventes': [
                ('montant_recu', 'FLOAT DEFAULT 0'),
                ('montant_hors_solde', 'FLOAT DEFAULT 0'),
                ('montant_solde_client', 'FLOAT DEFAULT 0'),
                ('montant_solde_groupe', 'FLOAT DEFAULT 0'),
                ('monnaie_rendue', 'FLOAT DEFAULT 0'),
                ('solde_client_avant', 'FLOAT DEFAULT 0'),
                ('solde_client_apres', 'FLOAT DEFAULT 0'),
                ('solde_groupe_avant', 'FLOAT DEFAULT 0'),
                ('solde_groupe_apres', 'FLOAT DEFAULT 0')
            ],
            'vente_lignes': [
                ('numero_vente', 'VARCHAR(80)'),
                ('produit_fournisseur', 'VARCHAR(120)'),
                ('produit_groupe_fournisseur', 'VARCHAR(120)'),
                ('produit_rayon', 'VARCHAR(120)'),
                ('produit_famille', 'VARCHAR(120)'),
                ('produit_section', 'VARCHAR(120)'),
                ('produit_conditionnement', 'INTEGER'),
                ('produit_codes_suivi', 'TEXT'),
                ('produit_dates_peremption', 'TEXT'),
                ('stock_unite_avant', 'FLOAT DEFAULT 0'),
                ('stock_sous_unite_avant', 'FLOAT DEFAULT 0'),
                ('stock_sous_sous_unite_avant', 'FLOAT DEFAULT 0')
            ]
        }

        for table, columns in columns_to_check.items():
            for column_name, column_type in columns:
                try:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {column_type};"))
                except Exception:
                    db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE vente_lignes DROP CONSTRAINT IF EXISTS vente_lignes_vente_id_fkey;"))
            db.session.execute(text("ALTER TABLE vente_lignes ALTER COLUMN vente_id DROP NOT NULL;"))
            db.session.execute(text("UPDATE vente_lignes SET numero_vente = ventes.numero_vente FROM ventes WHERE vente_lignes.vente_id = ventes.id AND (vente_lignes.numero_vente IS NULL OR vente_lignes.numero_vente = '');"))
        except Exception:
            db.session.rollback()

        db.session.commit()

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Enregistrement des blueprints
    from blueprints.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from blueprints.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    ensure_database_schema(app)

    return app

if __name__ == '__main__':
    app = create_app(os.getenv('FLASK_CONFIG') or 'default')
    app.run()
