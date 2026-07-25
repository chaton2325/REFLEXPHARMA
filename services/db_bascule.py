"""Bascule atomique de la base de données lors d'un changement de package de
licence qui change la base de connexion effective de l'application (voir
services/license_service.py::activate_with_code) : offline/hybrid <-> online,
ou online -> un autre online (migration d'hébergement côté ReflexPharma Admin).

À NE PAS confondre avec services/db_sync.py (miroir périodique MANUEL,
local -> en ligne uniquement, volontairement non transactionnel car la base en
ligne y reste jetable/toujours re-dérivable de la locale). Ici c'est l'inverse :
la base CIBLE devient la nouvelle source de vérité pour l'installation, donc une
coupure de courant en plein transfert ne doit jamais pouvoir la laisser à moitié
remplie -- et la reprise doit pouvoir se faire seule au redémarrage, avant même
qu'un administrateur se connecte (voir blueprints/license/__init__.py, qui
bloque tout accès tant qu'une bascule n'est pas 'done').

Garantie d'atomicité : services/pg_tools.py::restore_full_replace (psql
--single-transaction). Toute la restauration (remise à zéro du schéma cible
puis restauration complète) s'exécute dans une seule transaction Postgres ;
ON_ERROR_STOP=1 fait que tout code de retour non nul signifie que la
transaction a été annulée -- la base cible se retrouve alors EXACTEMENT dans
son état d'avant la tentative (vide, ou avec son ancien contenu intact), jamais
dans un état partiellement restauré. Ceci tient aussi bien pour la base locale
(serveur qu'on contrôle) que pour une base en ligne distante : le rollback sur
connexion coupée est une garantie du serveur Postgres cible, indépendante de ce
qui arrive au client. Hypothèse documentée : l'hébergeur en ligne doit tolérer
une transaction de la durée du restore complet (pas de statement_timeout
agressif, pas de pooler en mode transaction devant cette connexion).

Machine à états (table SQLite dédiée models/db_bascule.py::DbBascule, donc
lisible/écrivable même quand aucune base Postgres n'est joignable) :

    pending -> dumping -> restoring -> restored -> done
                              \\-> error (nouvelle tentative -> dumping)

Une tentative interrompue brutalement (process tué, coupure de courant) laisse
le statut figé sur 'dumping'/'restoring' sans jamais passer par 'error' : la
reprise (run_pending, appelée au redémarrage comme en tâche de fond périodique)
traite ces deux statuts exactement comme 'error' et refait le dump+restore
intégralement depuis zéro -- toujours sûr, la source n'est que lue et le restore
est transactionnel. Le statut intermédiaire 'restored' évite de refaire un
dump+restore (potentiellement long) si la coupure survient juste après un
restore déjà réussi, entre la fin de pg_restore et le basculement du pointeur de
connexion (config.py) : dans ce cas la reprise ne fait que finaliser.

Le verrou en mémoire (_worker_lock) suffit à empêcher deux workers concurrents
DANS CE PROCESS (retry manuel + reprise périodique de fond) : l'app tourne en
un seul process (voir app.py, app.run(...) sans multi-worker WSGI)."""
import os
import subprocess
import threading
import time
from datetime import datetime

from extensions import db
import config as app_config
from models.db_bascule import DbBascule
from services.pg_tools import find_binary, restore_full_replace

RETRY_INTERVAL_SECONDS = 120
_TIMEOUT_SECONDS = 1800  # 30 min : bascule ponctuelle, pas de contrainte de fréquence comme db_sync.py

_worker_lock = threading.Lock()


def _dump_path():
    return os.path.join(os.path.dirname(app_config.LICENSE_DB_PATH), 'db_bascule.dump')


def get_status():
    bascule = DbBascule.get_singleton()
    if bascule is None:
        return None
    return {
        'direction': bascule.direction,
        'target_package': bascule.target_package,
        'status': bascule.status,
        'attempts': bascule.attempts,
        'last_error': bascule.last_error,
        'started_at': bascule.started_at.isoformat() if bascule.started_at else None,
        'updated_at': bascule.updated_at.isoformat() if bascule.updated_at else None,
        'finished_at': bascule.finished_at.isoformat() if bascule.finished_at else None,
    }


def start(app, direction, target_package, source_url, target_url):
    """Enregistre une nouvelle bascule et lance immédiatement une première
    tentative en arrière-plan (non bloquant pour la requête HTTP qui l'a
    déclenchée). Ne fait rien si une bascule est déjà en cours/en attente."""
    existing = DbBascule.get_singleton()
    if existing is not None and existing.status != 'done':
        return False
    if existing is not None:
        db.session.delete(existing)

    bascule = DbBascule(
        direction=direction, source_url=source_url, target_url=target_url,
        target_package=target_package, status='pending',
    )
    db.session.add(bascule)
    db.session.commit()

    threading.Thread(target=run_pending, args=(app,), daemon=True).start()
    return True


def retry(app):
    """Relance une tentative depuis l'interface (bouton "Réessayer" de la page
    de statut). Non bloquant, comme start()."""
    bascule = DbBascule.get_singleton()
    if bascule is None or bascule.status == 'done':
        return False
    threading.Thread(target=run_pending, args=(app,), daemon=True).start()
    return True


def cancel():
    """Annule une bascule en attente/en erreur -- toujours sûr tant que le
    statut n'est pas 'done', puisque le pointeur de connexion (config.py) et
    LicenseCache.package ne sont modifiés qu'à la toute dernière étape
    (_finalize), jamais avant. Refuse si un worker écrit activement (dump/
    restore en cours) pour ne pas laisser un pg_dump/pg_restore orphelin."""
    if _worker_lock.locked():
        return False
    bascule = DbBascule.get_singleton()
    if bascule is None or bascule.status == 'done':
        return False
    db.session.delete(bascule)
    db.session.commit()
    return True


def start_background_watcher(app):
    """À appeler une fois au démarrage de l'app (voir app.py::create_app),
    inconditionnellement. Boucle de fond peu coûteuse (une requête SQLite
    toutes les RETRY_INTERVAL_SECONDS) qui sert à la fois de reprise immédiate
    après un redémarrage suite à une interruption brutale, ET de nouvelle
    tentative périodique tant qu'une bascule reste en échec -- fonctionne sans
    qu'aucun administrateur ne se connecte, voir blueprints/license/__init__.py."""
    def _loop():
        while True:
            run_pending(app)
            time.sleep(RETRY_INTERVAL_SECONDS)
    threading.Thread(target=_loop, daemon=True).start()


def run_pending(app):
    """Reprend/poursuit la bascule en attente. Sûr à appeler plusieurs fois en
    parallèle (verrou en mémoire) et après une interruption brutale à
    n'importe quelle étape (voir le docstring du module pour la machine à
    états). No-op rapide s'il n'y a rien à faire."""
    if not _worker_lock.acquire(blocking=False):
        return False
    try:
        with app.app_context():
            return _run_pending_locked()
    finally:
        _worker_lock.release()


def _run_pending_locked():
    bascule = DbBascule.get_singleton()
    if bascule is None or bascule.status == 'done':
        return False

    if bascule.status == 'restored':
        return _try_finalize(bascule)

    # pending / dumping / restoring / error : (re)part de zéro. Un statut
    # dumping/restoring retrouvé ici (plutôt que error) signifie que le worker
    # précédent a été tué avant d'avoir pu se marquer en erreur (coupure de
    # courant...) -- refaire le dump+restore intégralement est toujours sûr.
    bascule.status = 'dumping'
    bascule.attempts += 1
    bascule.last_error = None
    db.session.commit()

    dump_path = _dump_path()
    try:
        _run_dump(bascule.source_url, dump_path)

        if bascule.direction == 'to_local':
            _ensure_local_database_exists(bascule.target_url)

        bascule.status = 'restoring'
        db.session.commit()

        _run_restore(bascule.target_url, dump_path)

        bascule.status = 'restored'
        db.session.commit()

        return _try_finalize(bascule)
    except Exception as exc:
        bascule.status = 'error'
        bascule.last_error = str(exc)[:2000]
        db.session.commit()
        return False
    finally:
        try:
            os.remove(dump_path)
        except OSError:
            pass


def _try_finalize(bascule):
    try:
        _finalize(bascule)
        return True
    except Exception as exc:
        bascule.status = 'error'
        bascule.last_error = str(exc)[:2000]
        db.session.commit()
        return False


def _run_dump(source_url, dump_path):
    pg_dump = find_binary('pg_dump')
    if not pg_dump:
        raise RuntimeError(
            "pg_dump introuvable sur ce poste. Installez les outils client PostgreSQL "
            "(fournis avec le serveur PostgreSQL local) ou ajoutez-les au PATH."
        )
    result = subprocess.run(
        [pg_dump, source_url, '-Fc', '-f', dump_path],
        capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
    )
    if result.returncode != 0:
        raise RuntimeError(f"Échec de l'export de la base source : {result.stderr[:1000]}")


def _run_restore(target_url, dump_path):
    # Voir services/pg_tools.py::restore_full_replace pour le detail : remise a
    # zero atomique du schema cible (CASCADE) + restauration complete, en une
    # seule transaction psql --single-transaction -- contourne un bug connu de
    # pg_restore --clean sur des schemas avec dependances inter-tables (ex :
    # DROP CONSTRAINT users_pkey refuse tant que stock_modifications/
    # stock_securite en dependent encore).
    restore_full_replace(target_url, dump_path, timeout=_TIMEOUT_SECONDS)


def _ensure_local_database_exists(target_url):
    """CREATE DATABASE si besoin, UNIQUEMENT pour une cible locale (le rôle
    Postgres local est superuser d'après .env) -- jamais tenté côté hébergeur
    en ligne, dont on ne suppose aucun droit de création de base. CREATE
    DATABASE ne pouvant pas s'exécuter dans une transaction, cette étape est
    volontairement séparée de la restauration transactionnelle qui suit :
    interrompue ici, elle laisse au pire une base locale vide, sans risque
    (la tentative suivante la retrouve déjà créée, ou la recrée)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(target_url)
    dbname = url.database
    maintenance_url = url.set(database='postgres')

    engine = create_engine(maintenance_url, isolation_level='AUTOCOMMIT', connect_args={'connect_timeout': 10})
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {'name': dbname}
            ).first()
            if not exists:
                safe_name = dbname.replace('"', '""')
                conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
    finally:
        engine.dispose()


def _finalize(bascule):
    """Dernière étape, exécutée une fois la restauration confirmée réussie (ou
    rejouée si une coupure a eu lieu APRÈS un restore réussi mais AVANT que
    cette étape n'ait pu se terminer -- idempotente : le pointeur de connexion
    et le Setting hybride ne font qu'écraser avec la même valeur en cas de
    répétition, LicenseCache.package aussi)."""
    from config import write_db_override, clear_db_override
    from models.license_cache import LicenseCache

    if bascule.target_package == 'online':
        write_db_override(bascule.target_url)
    else:
        clear_db_override()

    if bascule.target_package == 'hybrid':
        # target_package == 'hybrid' implique toujours direction == 'to_local'
        # (l'Hybride tourne toujours sur la base locale, voir
        # services/license_service.py::activate_with_code) : l'URL "en ligne" à
        # retenir pour les futures synchronisations manuelles
        # (services/db_sync.py) est donc toujours source_url, celle qu'on quitte
        # -- à écrire DANS la nouvelle base locale (target_url), pas dans la
        # base en ligne elle-même.
        _write_online_database_url_setting(bascule.target_url, bascule.source_url)

    cache = LicenseCache.get_singleton()
    if cache is not None:
        cache.package = bascule.target_package

    bascule.status = 'done'
    bascule.finished_at = datetime.now()
    db.session.commit()


def _write_online_database_url_setting(local_db_url, online_url):
    """Écrit Setting['online_database_url'] = online_url DANS la base locale
    local_db_url (future base principale, mais pas encore liée au moteur
    SQLAlchemy principal de ce process -- un redémarrage est nécessaire pour
    ça, voir config.py) via une connexion courte séparée, même pattern que
    app.py::_migrate_legacy_license_cache."""
    from sqlalchemy import create_engine, text
    engine = create_engine(local_db_url, connect_args={'connect_timeout': 10})
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO settings (key, value, description)
                VALUES ('online_database_url', :url, :desc)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description
            """), {
                'url': online_url,
                'desc': "Base en ligne du package Hybride (synchronisation manuelle, voir Paramètres)",
            })
    finally:
        engine.dispose()
