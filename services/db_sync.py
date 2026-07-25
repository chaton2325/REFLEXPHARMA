"""Synchronisation package Hybride : miroir complet de la base locale vers la
base en ligne configurée dans Paramètres (Setting 'online_database_url'), via
pg_dump/pg_restore — mêmes outils client que ceux déjà installés avec le
serveur PostgreSQL local (voir _find_binary).

Miroir UNIQUEMENT dans ce sens (local -> en ligne, jamais l'inverse) : chaque
synchronisation REMPLACE entièrement le contenu de la base en ligne par une
copie exacte de la base locale à cet instant. Pas de fusion, pas de résolution
de conflits — la base en ligne n'est qu'une image en lecture, jamais modifiée
indépendamment. C'est un choix délibéré : une synchronisation bidirectionnelle
sur ~25 tables liées introduirait un risque réel d'incohérence de données pour
un bénéfice incertain."""
import glob
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime

from models.setting import Setting


def _find_binary(name):
    found = shutil.which(name)
    if found:
        return found
    # Windows : les outils client Postgres sont installés avec le serveur local,
    # mais pas toujours ajoutés au PATH.
    patterns = [
        rf'C:\Program Files\PostgreSQL\*\bin\{name}.exe',
        rf'C:\Program Files (x86)\PostgreSQL\*\bin\{name}.exe',
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    return None


def is_available():
    return bool(_find_binary('pg_dump') and _find_binary('pg_restore'))


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

    pg_dump = _find_binary('pg_dump')
    pg_restore = _find_binary('pg_restore')
    if not pg_dump or not pg_restore:
        raise RuntimeError(
            "pg_dump/pg_restore introuvables sur ce poste. Installez les outils client "
            "PostgreSQL (fournis avec le serveur PostgreSQL local) ou ajoutez-les au PATH."
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

        restore_result = subprocess.run(
            [pg_restore, '--clean', '--if-exists', '--no-owner', '--no-privileges',
             '-d', online_url, dump_path],
            capture_output=True, text=True, timeout=600
        )
        # --clean --if-exists évite les erreurs "n'existe pas" sur une base en ligne
        # vide au premier essai ; --no-owner/--no-privileges évite les avertissements
        # sur des rôles Postgres absents côté hébergeur en ligne. Un code de retour
        # non nul n'est traité comme un échec réel que s'il indique une connexion
        # impossible, pas de simples avertissements résiduels de pg_restore.
        if restore_result.returncode != 0 and ('FATAL' in restore_result.stderr or 'could not connect' in restore_result.stderr):
            raise RuntimeError(f"Échec de l'import vers la base en ligne : {restore_result.stderr[:1000]}")
    finally:
        try:
            os.remove(dump_path)
        except OSError:
            pass
