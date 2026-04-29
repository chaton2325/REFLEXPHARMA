import os
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

def fix_database():
    with app.app_context():
        print("Vérification et correction forcée de la base de données...")
        
        # 1. On s'assure que la table stock_reasons est propre
        try:
            db.session.execute(text("DROP TABLE IF EXISTS stock_reasons CASCADE"))
            db.session.commit()
            print("- Table stock_reasons supprimée pour réinitialisation.")
        except Exception as e:
            db.session.rollback()
            print(f"- Erreur drop stock_reasons: {e}")

        # 2. Création de la table stock_reasons via SQLAlchemy pour avoir la structure exacte
        try:
            # On importe ici pour s'assurer que le modèle est chargé
            from models.stock_reason import StockReason
            StockReason.__table__.create(db.engine)
            print("- Table stock_reasons recréée avec succès.")
        except Exception as e:
            print(f"- Note: La table stock_reasons existe peut-être déjà ou a été créée par create_all: {e}")

        # 3. Correction de stock_modification_logs
        try:
            # On ajoute la colonne reason_id si elle n'existe pas
            # PostgreSQL syntaxe pour ajouter une colonne si elle n'existe pas est un peu spéciale en SQL pur
            # mais on peut tenter l'ajout simple et catcher l'erreur si elle existe déjà
            db.session.execute(text("ALTER TABLE stock_modification_logs ADD COLUMN reason_id INTEGER"))
            db.session.commit()
            print("- Colonne reason_id ajoutée à stock_modification_logs.")
        except Exception as e:
            db.session.rollback()
            if "already exists" in str(e):
                print("- La colonne reason_id existe déjà dans stock_modification_logs.")
            else:
                print(f"- Erreur lors de l'ajout de reason_id: {e}")

        # 4. Ajout de la contrainte de clé étrangère
        try:
            db.session.execute(text("ALTER TABLE stock_modification_logs ADD CONSTRAINT fk_stock_modification_reason FOREIGN KEY (reason_id) REFERENCES stock_reasons (id)"))
            db.session.commit()
            print("- Contrainte de clé étrangère ajoutée.")
        except Exception as e:
            db.session.rollback()
            if "already exists" in str(e):
                print("- La contrainte existe déjà.")
            else:
                print(f"- Erreur lors de l'ajout de la contrainte: {e}")

        # 5. On s'assure que reason_id peut être NULL pour les anciens logs
        try:
            db.session.execute(text("ALTER TABLE stock_modification_logs ALTER COLUMN reason_id DROP NOT NULL"))
            db.session.execute(text("ALTER TABLE stock_modification_logs ALTER COLUMN reason DROP NOT NULL"))
            db.session.commit()
            print("- Colonnes configurées en nullable.")
        except Exception as e:
            db.session.rollback()
            print(f"- Note modification nullabilité: {e}")

        # 6. Seed des raisons par défaut
        try:
            from seed import seed
            seed()
            print("- Script de seed exécuté.")
        except Exception as e:
            print(f"- Erreur lors du seed: {e}")

        print("\nBase de données prête !")

if __name__ == '__main__':
    fix_database()
