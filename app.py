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
from models.raison_annulation_vente import RaisonAnnulationVente
from models.type_conge import TypeConge
from models.conge import Conge
from models.setting import Setting
from models.inventaire import Inventaire, InventaireLigne
from models.declaration_impot import DeclarationImpot
from models.declaration_caisse import DeclarationCaisse
from models.commande import Commande, CommandeLigne
from models.finance import OperationFinanciere, RaisonFinanciere
from models.cadeau_fidelite import CadeauFidelite
from models.carte_fidelite_commande import CarteFideliteCommande
from models.code_promo import CodePromo
from models.license_cache import LicenseCache
from models.db_bascule import DbBascule

from config import config

def ensure_database_schema(app):
    with app.app_context():
        db.create_all()

        # Initialize default settings if they don't exist
        if not Setting.query.filter_by(key='pharmacy_name').first():
            Setting.set_value('pharmacy_name', 'REFLEXPHARMA', 'Nom de la pharmacie affiché sur les tickets')

        columns_to_check = {
            'produits': [
                ('stock_securite', 'INTEGER DEFAULT 0'),
                # Programme de fidelite : points/unite achetee. NULL = pas de regle sur
                # ce produit (repli vers famille/rayon/section, voir Produit.points_fidelite_effectif).
                ('points_fidelite', 'INTEGER'),
                # Nombre d'unites par boite (ex: 10, 100...), utilise pour deriver
                # prix_sous_unite = prix_unite / taille_conditionnement.
                ('taille_conditionnement', 'INTEGER DEFAULT 1')
            ],
            'familles': [
                ('points_fidelite', 'INTEGER')
            ],
            'rayons': [
                ('points_fidelite', 'INTEGER')
            ],
            'sections': [
                ('points_fidelite', 'INTEGER')
            ],
            'clients': [
                # Solde de points de fidelite du client.
                ('points_fidelite', 'INTEGER DEFAULT 0')
            ],
            'commandes': [
                ('relance_de_numero', 'VARCHAR(40)')
            ],
            'stock_entries': [
                # Lie un lot de stock a la ligne de commande fournisseur dont il provient
                # (entree en stock rapide depuis le module Commandes) : reference souple,
                # sans contrainte FK ajoutee en ALTER (coherent avec le reste du self-heal).
                ('commande_ligne_id', 'INTEGER')
            ],
            'ventes': [
                ('montant_recu', 'FLOAT DEFAULT 0'),
                ('montant_hors_solde', 'FLOAT DEFAULT 0'),
                ('montant_solde_client', 'FLOAT DEFAULT 0'),
                ('montant_solde_groupe', 'FLOAT DEFAULT 0'),
                ('monnaie_rendue', 'FLOAT DEFAULT 0'),
                ('solde_client_avant', 'FLOAT DEFAULT 0'),
                ('solde_client_apres', 'FLOAT DEFAULT 0'),
                ('solde_groupe_avant', 'FLOAT DEFAULT 0'),
                ('solde_groupe_apres', 'FLOAT DEFAULT 0'),
                # Programme de fidelite : points gagnes sur cette vente.
                ('points_gagnes', 'INTEGER DEFAULT 0'),
                # Solde total de points fidelite du client juste apres cette vente.
                ('points_totaux_apres', 'INTEGER DEFAULT 0'),
                # Code promotionnel applique a cette vente (snapshot).
                ('code_promo_id', 'INTEGER'),
                ('code_promo_utilise', 'VARCHAR(50)'),
                ('code_promo_pourcentage', 'FLOAT'),
                ('code_promo_montant_deduit', 'FLOAT DEFAULT 0'),
                # Annulation de vente (voir raisons_annulation_vente / statut
                # 'annulee') : tous NULL tant que la vente n'est pas annulee.
                ('raison_annulation_id', 'INTEGER'),
                ('raison_annulation_nom', 'VARCHAR(200)'),
                ('annulation_commentaire', 'TEXT'),
                ('annulee_at', 'TIMESTAMP'),
                ('annulee_par_nom', 'VARCHAR(100)'),
                ('annulee_par_prenom', 'VARCHAR(100)'),
                ('annulee_par_email', 'VARCHAR(150)'),
                ('stock_restaure', 'BOOLEAN')
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
                ('stock_sous_sous_unite_avant', 'FLOAT DEFAULT 0'),
                # Snapshot du prix d'achat au moment de la vente (correction du calcul
                # des prix, juillet 2026) : NULL sur les ventes anterieures, pour ne pas
                # recalculer retroactivement un benefice deja facture/declare.
                ('prix_achat_unitaire', 'FLOAT'),
                # Lot reellement scanne (code_suivi) : sortie de stock precise au lot
                # physiquement vendu plutot qu'au FEFO arbitraire. NULL si pas de scan.
                ('stock_code_suivi', 'VARCHAR(255)'),
                # Points fidelite par unite au moment de la vente (snapshot).
                ('produit_points_fidelite', 'INTEGER')
            ],
            'stock_exit_logs': [
                # Snapshot du prix d'achat au moment de la sortie (formule benefice/TVA
                # alignee sur les ventes) : NULL sur les sorties anterieures.
                ('prix_achat_unite', 'FLOAT'),
                ('prix_achat_sous_unite', 'FLOAT'),
                ('prix_achat_sous_sous_unite', 'FLOAT')
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

        # Les raisons financieres sont typees (encaissement/decaissement) : les raisons
        # creees avant cette distinction sont classees en decaissement (a ajuster dans
        # l'interface si besoin), et l'unicite du nom devient une unicite par type.
        try:
            db.session.execute(text("ALTER TABLE raisons_financieres ADD COLUMN IF NOT EXISTS type VARCHAR(20);"))
            db.session.execute(text("UPDATE raisons_financieres SET type = 'decaissement' WHERE type IS NULL;"))
            db.session.execute(text("ALTER TABLE raisons_financieres ALTER COLUMN type SET NOT NULL;"))
            db.session.execute(text("ALTER TABLE raisons_financieres DROP CONSTRAINT IF EXISTS raisons_financieres_nom_key;"))
            db.session.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_raison_financiere_type_nom') THEN
                        ALTER TABLE raisons_financieres ADD CONSTRAINT uq_raison_financiere_type_nom UNIQUE (type, nom);
                    END IF;
                END $$;
            """))
        except Exception:
            db.session.rollback()

        # TVA et coefficient : desormais configures uniquement au niveau du PRODUIT
        # (voir models/produit.py), plus au niveau fournisseur/groupe fournisseur.
        # Backfill des produits existants (colonne encore nullable a ce stade) avec
        # leur valeur EFFECTIVE d'avant ce changement -- fournisseur, puis groupe,
        # puis defaut absolu -- avant de rendre la colonne obligatoire, pour ne pas
        # modifier silencieusement le prix de vente de produits deja en catalogue.
        try:
            db.session.execute(text(
                "UPDATE produits SET coefficient = fournisseurs.coefficient "
                "FROM fournisseurs WHERE produits.fournisseur_id = fournisseurs.id "
                "AND produits.coefficient IS NULL AND fournisseurs.coefficient IS NOT NULL;"
            ))
            db.session.execute(text(
                "UPDATE produits SET coefficient = groupes_fournisseurs.coefficient_defaut "
                "FROM fournisseurs, groupes_fournisseurs "
                "WHERE produits.fournisseur_id = fournisseurs.id "
                "AND fournisseurs.groupe_id = groupes_fournisseurs.id AND produits.coefficient IS NULL;"
            ))
            db.session.execute(text("UPDATE produits SET coefficient = 1.0 WHERE coefficient IS NULL;"))
            db.session.execute(text(
                "UPDATE produits SET tva = fournisseurs.tva "
                "FROM fournisseurs WHERE produits.fournisseur_id = fournisseurs.id "
                "AND produits.tva IS NULL AND fournisseurs.tva IS NOT NULL;"
            ))
            db.session.execute(text(
                "UPDATE produits SET tva = groupes_fournisseurs.tva_defaut "
                "FROM fournisseurs, groupes_fournisseurs "
                "WHERE produits.fournisseur_id = fournisseurs.id "
                "AND fournisseurs.groupe_id = groupes_fournisseurs.id AND produits.tva IS NULL;"
            ))
            db.session.execute(text("UPDATE produits SET tva = 20.0 WHERE tva IS NULL;"))
            db.session.execute(text("ALTER TABLE produits ALTER COLUMN coefficient SET DEFAULT 1.0;"))
            db.session.execute(text("ALTER TABLE produits ALTER COLUMN coefficient SET NOT NULL;"))
            db.session.execute(text("ALTER TABLE produits ALTER COLUMN tva SET DEFAULT 20.0;"))
            db.session.execute(text("ALTER TABLE produits ALTER COLUMN tva SET NOT NULL;"))
        except Exception:
            db.session.rollback()

        # Le CIP (code_produit) etait jusque-la unique sur toute la table : un
        # meme produit ne pouvait exister que chez un seul fournisseur. On passe
        # a une unicite par (code_produit, fournisseur_id), pour permettre au
        # meme CIP d'etre propose par plusieurs fournisseurs.
        try:
            db.session.execute(text("ALTER TABLE produits DROP CONSTRAINT IF EXISTS produits_code_produit_key;"))
            db.session.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_produit_code_produit_fournisseur') THEN
                        ALTER TABLE produits ADD CONSTRAINT uq_produit_code_produit_fournisseur UNIQUE (code_produit, fournisseur_id);
                    END IF;
                END $$;
            """))
        except Exception:
            db.session.rollback()

        # Une fois le backfill ci-dessus effectue, ces colonnes ne sont plus lues
        # nulle part dans l'application : nettoyage du schema.
        try:
            db.session.execute(text("ALTER TABLE fournisseurs DROP COLUMN IF EXISTS coefficient;"))
            db.session.execute(text("ALTER TABLE fournisseurs DROP COLUMN IF EXISTS tva;"))
            db.session.execute(text("ALTER TABLE groupes_fournisseurs DROP COLUMN IF EXISTS coefficient_defaut;"))
            db.session.execute(text("ALTER TABLE groupes_fournisseurs DROP COLUMN IF EXISTS tva_defaut;"))
        except Exception:
            db.session.rollback()

        db.session.commit()

def _migrate_legacy_license_cache(app):
    """Compatibilité ascendante : avant l'introduction du bind SQLite dédié
    (voir models/license_cache.py::__bind_key__), LicenseCache vivait dans la
    base PRINCIPALE (locale ou en ligne selon le package déjà actif). Les
    installations déjà activées avant ce changement (notamment la toute
    première pharmacie réelle, en package 'online' sur le VPS) ont donc leur
    véritable état de licence dans une table `license_cache` désormais
    orpheline de cette base — sans cette copie ponctuelle, elles seraient vues
    comme "jamais activées" au premier démarrage suivant la mise à jour, ce
    qui redemanderait un code déjà consommé (usage unique, voir ReflexPharma
    Admin services/licenses.py) au lieu de simplement continuer à fonctionner.

    Best-effort et silencieux, avec un délai de connexion volontairement court :
    si la base principale n'existe pas encore ou est injoignable (installation
    réellement neuve, notamment 100% en ligne avant sa toute première
    activation, voir config.py), on abandonne immédiatement sans lever
    d'exception ni rien écrire — l'app démarre alors normalement en mode
    "jamais activée", comme avant cette fonction."""
    main_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not main_uri:
        return

    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(main_uri, connect_args={'connect_timeout': 5})
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT * FROM license_cache ORDER BY id ASC LIMIT 1"
            )).mappings().first()
        engine.dispose()
    except Exception:
        return

    if row is None:
        return

    row = dict(row)
    cache = LicenseCache(
        activation_code=row.get('activation_code'),
        installation_token=row.get('installation_token'),
        pharmacy_id_remote=row.get('pharmacy_id_remote'),
        package=row.get('package') or 'offline',
        expires_at=row.get('expires_at'),
        expires_at_hmac=row.get('expires_at_hmac'),
        status=row.get('status') or 'active',
        last_verified_at=row.get('last_verified_at'),
        last_verify_attempt_at=row.get('last_verify_attempt_at'),
        last_verify_error=row.get('last_verify_error'),
        clock_high_water_mark=row.get('clock_high_water_mark'),
        created_at=row.get('created_at'),
        updated_at=row.get('updated_at'),
    )
    db.session.add(cache)
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

    # La devise choisie dans les paramètres est disponible dans TOUS les templates
    # (variable `devise` = symbole, ex: €, FCFA, $), sans rien passer aux vues.
    @app.context_processor
    def inject_currency():
        from utils.currencies import get_active_currency
        active = get_active_currency()
        return {'devise': active['symbole'], 'devise_code': active['code'], 'devise_nom': active['nom']}

    # Enregistrement des blueprints
    from blueprints.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from blueprints.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    from blueprints.license import license_bp
    app.register_blueprint(license_bp, url_prefix='/license')

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

    with app.app_context():
        # Toujours créé : fichier SQLite local, aucun réseau, aucune dépendance
        # à Postgres (voir models/license_cache.py::__bind_key__).
        db.create_all(bind_key='license')
        # Self-heal pour les fichiers license.db créés avant l'ajout de cette
        # colonne (voir models/db_bascule.py::hybrid_online_url) : create_all()
        # ne modifie jamais une table SQLite déjà existante. Connexion directe
        # sur l'engine du bind 'license' (db.session ne route pas du SQL brut
        # vers un bind non-défaut sans elle -- SQLAlchemy ne peut pas deviner
        # à quelle base "ALTER TABLE db_bascule" fait référence).
        try:
            with db.engines['license'].connect() as license_conn:
                license_conn.execute(text("ALTER TABLE db_bascule ADD COLUMN hybrid_online_url TEXT"))
                license_conn.commit()
        except Exception:
            pass
        if LicenseCache.query.first() is None:
            _migrate_legacy_license_cache(app)
        never_activated = LicenseCache.query.first() is None

    # Reprise d'une éventuelle bascule de base de données interrompue (coupure
    # de courant, fermeture brutale...) — voir services/db_bascule.py. Appelé
    # inconditionnellement (no-op rapide s'il n'y a rien en attente) et AVANT
    # même de savoir si la licence est valide : c'est cette table SQLite,
    # indépendante de la base Postgres principale, qui doit piloter la reprise
    # sans dépendre d'une connexion admin (voir aussi
    # blueprints/license/__init__.py::check_license, qui bloque l'accès tant
    # que la bascule n'est pas terminée).
    from services import db_bascule
    db_bascule.start_background_watcher(app)

    # La base PRINCIPALE (Postgres, locale ou en ligne selon la bascule) n'est
    # sollicitée que si un package est déjà connu (licence déjà activée au
    # moins une fois par le passé, même si expirée/révoquée depuis). Tant
    # qu'aucune activation n'a jamais eu lieu, on ne sait pas encore s'il
    # s'agit d'une installation hors ligne/hybride (Postgres local) ou 100% en
    # ligne — dans ce dernier cas, aucun Postgres local ne doit JAMAIS être
    # sollicité, pas même pour un simple self-heal de schéma. Le premier appel
    # a lieu juste après une activation réussie sans redémarrage requis (voir
    # blueprints/license/views.py), ou ici au démarrage suivant.
    if not never_activated:
        ensure_database_schema(app)

    return app

if __name__ == '__main__':
    from print_agent.launcher import start_print_agent
    start_print_agent()

    app = create_app(os.getenv('FLASK_CONFIG') or 'default')

    # Ne demarre le scheduler qu'une seule fois : sous le reloader Flask (debug=True),
    # ce bloc __main__ s'execute a la fois dans le process "surveillant" et dans le
    # process enfant reel (WERKZEUG_RUN_MAIN=true) ; on ne veut le job periodique que
    # dans ce dernier (ou toujours si le reloader est desactive).
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from services.license_scheduler import start_license_scheduler
        start_license_scheduler(app)

        from services.bootstrap import ensure_bootstrap_admin_user
        ensure_bootstrap_admin_user(app)

    # HTTPS local (necessaire pour l'acces camera sur le reseau local depuis un mobile).
    # Genere le certificat avec : python certs/generate_cert.py
    cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-dev.crt')
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs', 'reflexpharma-dev.key')
    ssl_context = (cert_path, key_path) if os.path.exists(cert_path) and os.path.exists(key_path) else None
    if ssl_context is None:
        print("Aucun certificat trouve (certs/reflexpharma-dev.crt) : serveur lance en HTTP simple.")
        print("Pour activer HTTPS (requis pour la camera sur mobile) : python certs/generate_cert.py")

    app.run(host='0.0.0.0', port=5003, debug=True, threaded=True, ssl_context=ssl_context)