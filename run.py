import os
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

def setup_database():
    with app.app_context():
        # 1. Création des tables manquantes
        db.create_all()
        
        # 2. Vérification et ajout automatique des colonnes manquantes (Self-Healing DB)
        # Cette partie permet de modifier la DB sans passer par des commandes manuelles
        engine = db.engine
        
        # Liste des colonnes à vérifier par table
        # Table 'users'
        cols_to_check = {
            'users': [
                ('date_prise_poste', 'DATE'),
                ('salaire_mensuel', 'FLOAT')
            ],
            'permissions': [
                # La table permissions est déjà gérée par create_all car nouvelle
            ],
            'stock_modifications': [
                ('numero_bl', 'VARCHAR(120)'),
                ('date_peremption', 'DATE'),
                ('code_suivi', 'VARCHAR(255)')
            ]
        }
        
        for table, columns in cols_to_check.items():
            for col_name, col_type in columns:
                try:
                    # Tente d'ajouter la colonne. Si elle existe, PostgreSQL renverra une erreur gérée.
                    query = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                    db.session.execute(text(query))
                except Exception:
                    db.session.rollback()
        
        db.session.commit()
        print("Structure de la base de données vérifiée et mise à jour.")

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
