import json
import os
from dotenv import load_dotenv

load_dotenv()

# Package "en ligne" (100% online, voir blueprints/license) : à l'activation d'un
# code de ce package, l'app enregistre ici l'URL de la base en ligne attribuée par
# ReflexPharma Admin. Un fichier local (et non une valeur en base) est nécessaire
# car c'est justement CE fichier qui détermine à quelle base se connecter au
# prochain démarrage — un mécanisme purement interne, invisible pour l'utilisateur
# (qui configure/consulte tout depuis Paramètres, jamais ce fichier à la main).
DB_OVERRIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'db_override.json')

# license_cache vit dans SON PROPRE fichier SQLite, complètement indépendant de
# Postgres (local ou en ligne) — voir models/license_cache.py::__bind_key__.
# Objectif : une installation qui n'a encore jamais été activée (donc dont on ne
# connaît pas encore le package) ne doit JAMAIS avoir besoin d'un Postgres local
# joignable rien que pour afficher l'écran d'activation. Seule la base
# principale (celle des ~25 modèles métier) dépend de DATABASE_LOCAL_URL / de la
# bascule en ligne, et n'est sollicitée qu'une fois le package connu (voir
# app.py::create_app, ensure_database_schema appelé conditionnellement).
LICENSE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'license.db')
os.makedirs(os.path.dirname(LICENSE_DB_PATH), exist_ok=True)  # SQLite exige que le dossier existe déjà


def _resolve_database_uri():
    """URL de connexion effective de l'application. Package hors ligne/hybride :
    toujours DATABASE_LOCAL_URL (comportement historique, aucun changement). Package
    en ligne : l'URL en ligne attribuée, une fois enregistrée par
    services/license_service.py::activate_with_code (nécessite un redémarrage pour
    prendre effet, le moteur SQLAlchemy étant créé une seule fois au démarrage)."""
    if os.path.exists(DB_OVERRIDE_PATH):
        try:
            with open(DB_OVERRIDE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('database_url'):
                return data['database_url']
        except (OSError, ValueError):
            pass
    return os.getenv('DATABASE_LOCAL_URL')


def write_db_override(database_url):
    """Enregistre l'URL de la base en ligne à utiliser dès le prochain démarrage
    (package 'online'). Appelé uniquement par services/db_bascule.py, après
    confirmation que la copie des données a réussi (voir son docstring) — jamais
    avant, pour ne jamais basculer la connexion sur une base incomplète.

    Écriture atomique (fichier temporaire + os.replace, garanti atomique par
    l'OS même sur le même volume Windows) : une coupure de courant en plein
    milieu de l'écriture laisse alors soit l'ancien contenu intact, soit le
    nouveau intégralement écrit, jamais un JSON tronqué illisible au prochain
    démarrage."""
    os.makedirs(os.path.dirname(DB_OVERRIDE_PATH), exist_ok=True)
    tmp_path = DB_OVERRIDE_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump({'database_url': database_url}, f)
    os.replace(tmp_path, DB_OVERRIDE_PATH)


def clear_db_override():
    """Supprime le pointeur vers une base en ligne : au prochain démarrage,
    _resolve_database_uri() retombe alors sur DATABASE_LOCAL_URL. Appelé par
    services/db_bascule.py lors d'une bascule vers un package offline/hybrid,
    après confirmation que la copie des données vers la base locale a réussi."""
    try:
        os.remove(DB_OVERRIDE_PATH)
    except FileNotFoundError:
        pass


def has_db_override():
    return os.path.exists(DB_OVERRIDE_PATH)


# Filet de sécurité pour le tout premier compte admin créé automatiquement
# (voir services/bootstrap.py) : l'email envoyé via ReflexPharma Admin peut
# échouer (SMTP, réseau...), donc le mot de passe généré est AUSSI écrit ici et
# affiché sur la page de connexion tant que ce compte n'a jamais servi (voir
# blueprints/auth/views.py) — garantit que l'accès n'est jamais perdu même si
# l'email n'arrive pas.
FIRST_LOGIN_CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'first_admin_credentials.json')


def write_first_login_credentials(username, password):
    os.makedirs(os.path.dirname(FIRST_LOGIN_CREDENTIALS_PATH), exist_ok=True)
    with open(FIRST_LOGIN_CREDENTIALS_PATH, 'w', encoding='utf-8') as f:
        json.dump({'username': username, 'password': password}, f)


def read_first_login_credentials():
    if not os.path.exists(FIRST_LOGIN_CREDENTIALS_PATH):
        return None
    try:
        with open(FIRST_LOGIN_CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def clear_first_login_credentials():
    try:
        os.remove(FIRST_LOGIN_CREDENTIALS_PATH)
    except OSError:
        pass


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-me')
    # Utilisation de DATABASE_LOCAL_URL par défaut comme vu dans testDatabase.py.py
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    SQLALCHEMY_BINDS = {
        'license': 'sqlite:///' + LICENSE_DB_PATH.replace(os.sep, '/'),
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

    # Module de licence : URL de l'API de ReflexPharma Admin, secret HMAC local
    # (protège license_cache.expires_at_hmac contre une modification directe en base
    # locale) et intervalle de re-vérification périodique en arrière-plan.
    LICENSE_ADMIN_API_BASE_URL = os.getenv('LICENSE_ADMIN_API_BASE_URL', 'http://localhost:5001')
    LICENSE_HMAC_SECRET_LOCAL = os.getenv('LICENSE_HMAC_SECRET_LOCAL', 'change-me-local-secret')
    LICENSE_CHECK_INTERVAL_MINUTES = int(os.getenv('LICENSE_CHECK_INTERVAL_MINUTES', '60'))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
