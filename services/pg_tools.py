"""Localisation des outils client PostgreSQL (pg_dump/pg_restore/psql), partagée
entre services/db_sync.py (miroir périodique manuel du package Hybride) et
services/db_bascule.py (bascule atomique de base au changement de package)."""
import glob
import os
import shutil
import subprocess
import tempfile


def find_binary(name):
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
    return bool(find_binary('pg_dump') and find_binary('pg_restore') and find_binary('psql'))


# Réglages de préambule que pg_restore peut émettre mais qu'un serveur CIBLE
# plus ancien que les outils client locaux ne reconnaît pas -- ex :
# "transaction_timeout", paramètre introduit en PostgreSQL 17 seulement.
# Rencontré en pratique : outils client locaux en 17, base en ligne hébergée
# sur un Postgres antérieur -> "ERROR: unrecognized configuration parameter
# transaction_timeout", qui fait échouer toute la transaction (--single-
# transaction), donc toute la bascule, alors qu'aucune donnée n'est en cause.
# Ne concerne que le comportement de LA SESSION de restauration elle-même,
# jamais les données : sans risque à retirer.
_INCOMPATIBLE_PREAMBLE_PREFIXES = (
    'SET transaction_timeout',
)


def _strip_incompatible_preamble(sql_text):
    return ''.join(
        line for line in sql_text.splitlines(keepends=True)
        if not line.lstrip().startswith(_INCOMPATIBLE_PREAMBLE_PREFIXES)
    )


def restore_full_replace(target_url, dump_path, timeout=1800):
    """Restaure dump_path (format -Fc de pg_dump) dans target_url en
    REMPLACEMENT COMPLET et ATOMIQUE de son contenu actuel : remise à zéro du
    schéma 'public' (DROP SCHEMA ... CASCADE ; CREATE SCHEMA public) puis
    restauration intégrale -- tout dans UNE SEULE transaction
    (psql --single-transaction), qui annule tout aussi bien en cas d'erreur que
    d'interruption brutale (coupure de courant, process tué...) : le schéma
    cible se retrouve alors exactement dans son état d'avant l'appel, jamais
    dans un état intermédiaire (ni vidé, ni partiellement restauré).

    Pourquoi pas simplement pg_restore --clean --if-exists -d ... : sur un
    schéma avec des dépendances entre tables (une clé étrangère référençant la
    clé primaire d'une autre table), --clean supprime parfois les objets dans
    un ordre qui ne respecte pas ces dépendances ("cannot drop constraint ...
    because other objects depend on it") -- une limitation connue de
    pg_restore, pas spécifique à un schéma particulier. Vider tout le schéma
    par CASCADE en une fois contourne entièrement ce calcul d'ordre objet par
    objet : pg_restore ne sert plus alors qu'à GÉNÉRER le SQL de restauration
    (-f, sans se connecter à la base), c'est psql qui l'exécute et porte la
    transaction unique.

    N'agit QUE sur le schéma 'public' (seul schéma utilisé par cette
    application) -- hypothèse à revoir si d'autres schémas sont introduits."""
    pg_restore = find_binary('pg_restore')
    psql = find_binary('psql')
    if not pg_restore or not psql:
        raise RuntimeError(
            "pg_restore/psql introuvables sur ce poste. Installez les outils client "
            "PostgreSQL (fournis avec le serveur PostgreSQL local) ou ajoutez-les au PATH."
        )

    fd, script_path = tempfile.mkstemp(suffix='.sql', prefix='reflexpharma_restore_')
    os.close(fd)
    try:
        gen = subprocess.run(
            [pg_restore, '--no-owner', '--no-privileges', '-f', script_path, dump_path],
            capture_output=True, text=True, timeout=timeout
        )
        if gen.returncode != 0:
            raise RuntimeError(f"Échec de génération du script de restauration : {gen.stderr[:1000]}")

        with open(script_path, 'r', encoding='utf-8') as f:
            generated_sql = _strip_incompatible_preamble(f.read())
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write("DROP SCHEMA IF EXISTS public CASCADE;\nCREATE SCHEMA public;\n")
            f.write(generated_sql)

        result = subprocess.run(
            [psql, '--single-transaction', '--set', 'ON_ERROR_STOP=1', '--quiet',
             '-d', target_url, '-f', script_path],
            capture_output=True, text=True, timeout=timeout
        )
        # --single-transaction + ON_ERROR_STOP=1 : toute erreur interrompt psql
        # avant le COMMIT final -- la transaction ouverte est alors annulée
        # automatiquement par Postgres à la fermeture de la connexion, aussi
        # bien sur une vraie erreur SQL que sur une interruption brutale du
        # process lui-même. Un code de retour non nul signifie donc toujours
        # que rien n'a été appliqué.
        if result.returncode != 0:
            raise RuntimeError(f"Échec de la restauration vers la base cible : {(result.stderr or result.stdout)[:1500]}")
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass
