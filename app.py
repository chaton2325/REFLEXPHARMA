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
from models.setting import Setting
from models.inventaire import Inventaire, InventaireLigne

from config import config

def ensure_database_schema(app):
    with app.app_context():
        db.create_all()

        # Initialize default settings if they don't exist
        if not Setting.query.filter_by(key='pharmacy_name').first():
            Setting.set_value('pharmacy_name', 'REFLEXPHARMA', 'Nom de la pharmacie affiché sur les tickets')

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

    @app.route('/ca-cert')
    def download_ca_cert():
        """Sert le certificat de l'autorite de certification locale (fichier public,
        pas la cle privee) pour l'installer facilement depuis un telephone :
        ouvrir http(s)://<ip-serveur>:5000/ca-cert dans le navigateur du telephone."""
        from flask import send_file, abort
        cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-ca.crt')
        if not os.path.exists(cert_path):
            abort(404, description="Certificat CA non genere. Lancez : python certs/generate_cert.py")
        return send_file(
            cert_path,
            mimetype='application/x-x509-ca-cert',
            as_attachment=True,
            download_name='reflexpharma-ca.crt'
        )

    ensure_database_schema(app)

    return app

if __name__ == '__main__':
    from print_agent.launcher import start_print_agent
    start_print_agent()

    app = create_app(os.getenv('FLASK_CONFIG') or 'default')

    # HTTPS local (necessaire pour l'acces camera sur le reseau local depuis un mobile).
    # Genere le certificat avec : python certs/generate_cert.py
    cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-dev.crt')
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-dev.key')
    ssl_context = (cert_path, key_path) if os.path.exists(cert_path) and os.path.exists(key_path) else None
    if ssl_context is None:
        print("Aucun certificat trouve (certs/reflexpharma-dev.crt) : serveur lance en HTTP simple.")
        print("Pour activer HTTPS (requis pour la camera sur mobile) : python certs/generate_cert.py")

    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, ssl_context=ssl_context)
