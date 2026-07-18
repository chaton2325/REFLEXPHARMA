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
                ('salaire_mensuel', 'FLOAT'),
                ('username', 'VARCHAR(80)')
            ],
            'permissions': [
                # La table permissions est déjà gérée par create_all car nouvelle
            ],
            'stock_entries': [
                ('qr_tire', 'BOOLEAN DEFAULT FALSE')
            ],
            'produits': [
                ('stock_securite', 'INTEGER DEFAULT 0')
            ],
            'commandes': [
                ('relance_de_numero', 'VARCHAR(40)')
            ],
            'inventaires': [
                ('date_planifiee', 'TIMESTAMP')
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
                # Snapshot du prix d'achat au moment de la sortie (formule benefice/TVA
                # alignee sur les ventes) : NULL sur les sorties anterieures.
                ('prix_achat_unite', 'FLOAT'),
                ('prix_achat_sous_unite', 'FLOAT'),
                ('prix_achat_sous_sous_unite', 'FLOAT'),
                ('tva_pourcentage', 'FLOAT DEFAULT 0'),
                ('total_sortie_ht', 'FLOAT DEFAULT 0'),
                ('total_sortie_ttc', 'FLOAT DEFAULT 0')
            ],
            'groupes_clients': [
                ('pourcentage_absorption', 'FLOAT DEFAULT 0')
            ],
            'ventes': [
                ('numero_vente', 'VARCHAR(80)'),
                ('statut', 'VARCHAR(30) DEFAULT \'validee\''),
                ('mode_paiement', 'VARCHAR(50) DEFAULT \'especes\''),
                ('note', 'TEXT'),
                ('client_id', 'INTEGER'),
                ('client_matricule', 'VARCHAR(50)'),
                ('client_nom', 'VARCHAR(120)'),
                ('client_prenom', 'VARCHAR(120)'),
                ('client_email', 'VARCHAR(150)'),
                ('groupe_client_id', 'INTEGER'),
                ('groupe_client_nom', 'VARCHAR(120)'),
                ('groupe_absorption_pourcentage', 'FLOAT DEFAULT 0'),
                ('total_ht', 'FLOAT DEFAULT 0'),
                ('total_tva', 'FLOAT DEFAULT 0'),
                ('total_ttc', 'FLOAT DEFAULT 0'),
                ('montant_recu', 'FLOAT DEFAULT 0'),
                ('montant_hors_solde', 'FLOAT DEFAULT 0'),
                ('montant_solde_client', 'FLOAT DEFAULT 0'),
                ('montant_solde_groupe', 'FLOAT DEFAULT 0'),
                ('monnaie_rendue', 'FLOAT DEFAULT 0'),
                ('solde_client_avant', 'FLOAT DEFAULT 0'),
                ('solde_client_apres', 'FLOAT DEFAULT 0'),
                ('solde_groupe_avant', 'FLOAT DEFAULT 0'),
                ('solde_groupe_apres', 'FLOAT DEFAULT 0'),
                ('auteur_id', 'INTEGER'),
                ('auteur_nom', 'VARCHAR(100)'),
                ('auteur_prenom', 'VARCHAR(100)'),
                ('auteur_email', 'VARCHAR(150)'),
                ('created_at', 'TIMESTAMP'),
                ('updated_at', 'TIMESTAMP')
            ],
            'vente_lignes': [
                ('vente_id', 'INTEGER'),
                ('numero_vente', 'VARCHAR(80)'),
                ('produit_id', 'INTEGER'),
                ('produit_code', 'VARCHAR(50)'),
                ('produit_nom', 'VARCHAR(200)'),
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
                ('stock_sous_sous_unite_avant', 'FLOAT DEFAULT 0'),
                ('unite', 'VARCHAR(30) DEFAULT \'unite\''),
                ('quantite', 'FLOAT DEFAULT 1'),
                ('prix_unitaire_ht', 'FLOAT DEFAULT 0'),
                ('prix_unitaire_ttc', 'FLOAT DEFAULT 0'),
                # Snapshot du prix d'achat au moment de la vente (correction du calcul
                # des prix, juillet 2026) : NULL sur les ventes anterieures, pour ne pas
                # recalculer retroactivement un benefice deja facture/declare.
                ('prix_achat_unitaire', 'FLOAT'),
                ('tva_pourcentage', 'FLOAT DEFAULT 0'),
                ('total_ht', 'FLOAT DEFAULT 0'),
                ('total_tva', 'FLOAT DEFAULT 0'),
                ('total_ttc', 'FLOAT DEFAULT 0'),
                ('created_at', 'TIMESTAMP')
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

        # Les ventes doivent rester des snapshots historiques autonomes :
        # aucune contrainte de clé étrangère ne doit pointer vers vente_lignes.
        constraints_to_drop = {
            'vente_lignes': [
                'vente_lignes_vente_id_fkey'
            ]
        }
        for table, constraints in constraints_to_drop.items():
            for constraint_name in constraints:
                try:
                    db.session.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name};"))
                except Exception:
                    db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE vente_lignes ALTER COLUMN vente_id DROP NOT NULL;"))
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(text("UPDATE vente_lignes SET numero_vente = ventes.numero_vente FROM ventes WHERE vente_lignes.vente_id = ventes.id AND (vente_lignes.numero_vente IS NULL OR vente_lignes.numero_vente = '');"))
        except Exception:
            db.session.rollback()
        
        db.session.commit()
        print("Structure de la base de données vérifiée et mise à jour.")

if __name__ == '__main__':
    from print_agent.launcher import start_print_agent
    start_print_agent()

    setup_database()

    # HTTPS local (necessaire pour l'acces camera sur le reseau local depuis un mobile).
    # Genere le certificat avec : python certs/generate_cert.py
    cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-dev.crt')
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-dev.key')
    ssl_context = (cert_path, key_path) if os.path.exists(cert_path) and os.path.exists(key_path) else None
    if ssl_context is None:
        print("Aucun certificat trouve (certs/reflexpharma-dev.crt) : serveur lance en HTTP simple.")
        print("Pour activer HTTPS (requis pour la camera sur mobile) : python certs/generate_cert.py")

    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, ssl_context=ssl_context)
