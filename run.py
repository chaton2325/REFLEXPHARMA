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
            'stock_entries': [
                ('qr_tire', 'BOOLEAN DEFAULT FALSE')
            ],
            'stock_modification_logs': [
                ('numero_bl', 'VARCHAR(120)'),
                ('date_peremption', 'DATE'),
                ('code_suivi', 'VARCHAR(255)'),
                ('old_qr_tire', 'BOOLEAN DEFAULT FALSE'),
                ('new_qr_tire', 'BOOLEAN DEFAULT FALSE')
            ],
            'stock_exit_logs': [
                ('fournisseur_id', 'INTEGER'),
                ('fournisseur_nom', 'VARCHAR(100)'),
                ('groupe_fournisseur_id', 'INTEGER'),
                ('groupe_fournisseur_nom', 'VARCHAR(100)'),
                ('mise_en_stock_at', 'TIMESTAMP'),
                ('mise_en_stock_user_nom', 'VARCHAR(100)'),
                ('mise_en_stock_user_prenom', 'VARCHAR(100)'),
                ('mise_en_stock_user_email', 'VARCHAR(150)'),
                ('prix_unite_ht', 'FLOAT DEFAULT 0'),
                ('prix_sous_unite_ht', 'FLOAT DEFAULT 0'),
                ('prix_sous_sous_unite_ht', 'FLOAT DEFAULT 0'),
                ('prix_unite_ttc', 'FLOAT DEFAULT 0'),
                ('prix_sous_unite_ttc', 'FLOAT DEFAULT 0'),
                ('prix_sous_sous_unite_ttc', 'FLOAT DEFAULT 0'),
                ('tva_pourcentage', 'FLOAT DEFAULT 0'),
                ('total_sortie_ht', 'FLOAT DEFAULT 0'),
                ('total_sortie_ttc', 'FLOAT DEFAULT 0')
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

        # La table stock_exit_logs doit rester un journal brut sans identifiants
        # pointant vers d'autres tables. On supprime les anciennes colonnes *_id.
        columns_to_drop = {
            'stock_exit_logs': [
                'stock_id',
                'produit_id',
                'user_id',
                'reason_id',
                'fournisseur_id',
                'groupe_fournisseur_id'
            ]
        }
        for table, columns in columns_to_drop.items():
            for col_name in columns:
                try:
                    db.session.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col_name};"))
                except Exception:
                    db.session.rollback()
        
        db.session.commit()
        print("Structure de la base de données vérifiée et mise à jour.")

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
