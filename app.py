import os
from flask import Flask, redirect, url_for
from extensions import db, login_manager, migrate
from flask_migrate import upgrade

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

from config import config

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

    return app

if __name__ == '__main__':
    app = create_app(os.getenv('FLASK_CONFIG') or 'default')
    with app.app_context():
        # Crée les tables initiales si elles n'existent pas
        db.create_all()
        # Note: Dans un environnement pro, on utiliserait 'flask db upgrade'
        # Pour ce projet, on garde db.create_all() pour la simplicité initiale
    app.run()
