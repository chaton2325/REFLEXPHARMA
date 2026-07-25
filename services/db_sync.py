"""Synchronisation package Hybride : miroir complet de la base locale vers la
base en ligne configurée dans Paramètres (Setting 'online_database_url'), via
pg_dump/pg_restore — mêmes outils client que ceux déjà installés avec le
serveur PostgreSQL local (voir services/pg_tools.py::find_binary).

Miroir UNIQUEMENT dans ce sens (local -> en ligne, jamais l'inverse) : chaque
synchronisation REMPLACE entièrement le contenu de la base en ligne par une
copie exacte de la base locale à cet instant. Pas de fusion, pas de résolution
de conflits — la base en ligne n'est qu'une image en lecture, jamais modifiée
indépendamment. C'est un choix délibéré : une synchronisation bidirectionnelle
sur ~25 tables liées introduirait un risque réel d'incohérence de données pour
un bénéfice incertain."""
import os
import subprocess
import tempfile
import threading
from datetime import datetime

from models.setting import Setting
from services.pg_tools import find_binary, is_available, restore_full_replace


def get_status():
    return {
        'status': Setting.get_value('sync_status', 'idle'),
        'started_at': Setting.get_value('sync_started_at'),
        'finished_at': Setting.get_value('sync_finished_at'),
        'error': Setting.get_value('sync_error'),
    }


def start_sync(app):
    """Démarre la synchronisation en arrière-plan (thread daemon), non-bloquant
    pour la requête HTTP qui l'a déclenchée. Ne fait rien si une synchro est
    déjà en cours (évite deux pg_dump/pg_restore concurrents)."""
    if Setting.get_value('sync_status') == 'running':
        return False

    Setting.set_value('sync_status', 'running')
    Setting.set_value('sync_started_at', datetime.now().isoformat())
    Setting.set_value('sync_error', '')

    threading.Thread(target=_run_sync, args=(app,), daemon=True).start()
    return True


def _run_sync(app):
    with app.app_context():
        try:
            _do_sync(app.config['SQLALCHEMY_DATABASE_URI'])
            Setting.set_value('sync_status', 'success')
        except Exception as exc:
            Setting.set_value('sync_status', 'error')
            Setting.set_value('sync_error', str(exc)[:2000])
        finally:
            Setting.set_value('sync_finished_at', datetime.now().isoformat())


def _do_sync(local_url):
    online_url = (Setting.get_value('online_database_url', '') or '').strip()
    if not online_url:
        raise RuntimeError("Aucune base de données en ligne configurée dans Paramètres.")

    pg_dump = find_binary('pg_dump')
    if not pg_dump:
        raise RuntimeError(
            "pg_dump introuvable sur ce poste. Installez les outils client PostgreSQL "
            "(fournis avec le serveur PostgreSQL local) ou ajoutez-les au PATH."
        )

    fd, dump_path = tempfile.mkstemp(suffix='.dump', prefix='reflexpharma_sync_')
    os.close(fd)
    try:
        dump_result = subprocess.run(
            [pg_dump, local_url, '-Fc', '-f', dump_path],
            capture_output=True, text=True, timeout=600
        )
        if dump_result.returncode != 0:
            raise RuntimeError(f"Échec de l'export de la base locale : {dump_result.stderr[:1000]}")

        # Voir services/pg_tools.py::restore_full_replace : remise a zero
        # atomique du schema en ligne (CASCADE) + restauration complete, en une
        # seule transaction -- contourne un bug connu de pg_restore --clean sur
        # des schemas avec dependances inter-tables (ex : DROP CONSTRAINT
        # users_pkey refuse tant que stock_modifications/stock_securite en
        # dependent encore), et gere aussi bien une base en ligne vide au
        # premier essai qu'un role Postgres absent cote hebergeur (--no-owner/
        # --no-privileges).
        restore_full_replace(online_url, dump_path, timeout=600)
    finally:
        try:
            os.remove(dump_path)
        except OSError:
            pass
