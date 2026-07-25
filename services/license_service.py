"""État local de la licence (models/license_cache.py) : calcul/vérification du HMAC
anti-fraude, détection de recul d'horloge, et synchronisation avec l'API de
ReflexPharma Admin (services/license_client.py).

Le blueprint `license` (blueprints/license) est le seul consommateur direct de
get_state()/is_valid() dans le hook before_app_request : cette lecture ne fait
JAMAIS d'appel réseau, ce qui garantit le fonctionnement hors-ligne jusqu'à
expires_at. Les appels réseau n'ont lieu qu'à l'activation (activate_with_code) et
lors de la re-vérification périodique (refresh_from_server, appelée par
services/license_scheduler.py)."""
import hmac
import hashlib
from datetime import datetime, timedelta

from flask import current_app

from extensions import db
from models.license_cache import LicenseCache
from services import license_client

# Tolérance sur le recul d'horloge (dérive NTP/fuseau normale) avant de suspecter
# une manipulation volontaire de l'horloge système pour prolonger l'usage hors-ligne.
CLOCK_ROLLBACK_TOLERANCE = timedelta(minutes=5)


def compute_local_hmac(activation_code, expires_at):
    secret = current_app.config['LICENSE_HMAC_SECRET_LOCAL']
    message = f"{activation_code}|{expires_at.isoformat()}"
    return hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()


def _hmac_matches(cache):
    if not cache.expires_at or not cache.expires_at_hmac:
        return False
    expected = compute_local_hmac(cache.activation_code, cache.expires_at)
    return hmac.compare_digest(expected, cache.expires_at_hmac)


def _clock_rolled_back(cache):
    if not cache.clock_high_water_mark:
        return False
    return datetime.now() < cache.clock_high_water_mark - CLOCK_ROLLBACK_TOLERANCE


def _evaluate_reason(cache):
    if cache is None:
        return 'not_activated'
    if cache.expires_at is None or cache.expires_at_hmac is None:
        return 'not_activated'
    if not _hmac_matches(cache):
        return 'tampered'
    if cache.status == 'revoked':
        return 'revoked'
    if cache.status == 'tampered':
        return 'tampered'
    if _clock_rolled_back(cache):
        return 'clock_rollback'
    if datetime.now() > cache.expires_at:
        return 'expired'
    return 'ok'


class LicenseState:
    def __init__(self, cache):
        self.cache = cache
        self.reason = _evaluate_reason(cache)

    @property
    def never_activated(self):
        return self.cache is None

    def is_valid(self):
        return self.reason == 'ok'


def mask_activation_code(code):
    """Affichage partiel du code (ex: RXPH-****-****-K9U7) pour la page Paramètres :
    consultable sans exposer le code complet à l'écran (capture d'écran, épaule...)."""
    if not code:
        return ''
    parts = code.split('-')
    if len(parts) == 4:
        return f"{parts[0]}-****-****-{parts[3]}"
    return code


def get_state():
    """Lecture pure locale (aucun appel réseau) de l'état de licence, avec
    marquage 'tampered' persistant si le HMAC ne correspond plus, et mise à jour
    peu fréquente du repère anti-recul d'horloge."""
    cache = LicenseCache.get_singleton()
    if cache is None:
        return LicenseState(None)

    dirty = False
    if _evaluate_reason(cache) == 'tampered' and cache.status != 'tampered':
        cache.status = 'tampered'
        dirty = True

    now = datetime.now()
    if not cache.clock_high_water_mark or now - cache.clock_high_water_mark > timedelta(minutes=1):
        if not cache.clock_high_water_mark or now > cache.clock_high_water_mark:
            cache.clock_high_water_mark = now
            dirty = True

    if dirty:
        db.session.commit()

    return LicenseState(cache)


def activate_with_code(activation_code, pharmacy_name=None, online_database_url=None):
    """Active un code auprès de l'API distante et (ré)écrit le cache local.
    Lève license_client.LicenseApiUnavailable ou LicenseApiRejected en cas d'échec :
    à l'appelant (vue d'activation) d'afficher le message adapté.

    Retourne (state, restart_required) : restart_required est True uniquement
    pour un package 'online' fraîchement activé — la bascule de base de données
    (config.py::write_db_override) ne prend effet qu'au prochain démarrage,
    le moteur SQLAlchemy étant créé une seule fois au lancement de l'app."""
    import config as app_config
    from models.setting import Setting

    data = license_client.activate(activation_code, pharmacy_name=pharmacy_name,
                                    online_database_url=online_database_url)

    expires_at = datetime.fromisoformat(data['expires_at'])
    now = datetime.now()
    package = data.get('package', 'offline')
    database_url = data.get('database_url')

    cache = LicenseCache.get_singleton()
    if cache is None:
        cache = LicenseCache()
        db.session.add(cache)

    cache.activation_code = activation_code
    cache.installation_token = data['installation_token']
    cache.pharmacy_id_remote = data.get('pharmacy_id')
    cache.package = package
    cache.expires_at = expires_at
    cache.expires_at_hmac = compute_local_hmac(activation_code, expires_at)
    cache.status = 'active'
    cache.last_verified_at = now
    cache.last_verify_attempt_at = now
    cache.last_verify_error = None
    cache.clock_high_water_mark = now

    db.session.commit()

    restart_required = False
    if package == 'hybrid' and database_url:
        Setting.set_value('online_database_url', database_url,
                           "Base en ligne du package Hybride (synchronisation manuelle, voir Paramètres)")
    elif package == 'online' and database_url:
        # Pas de Setting.set_value ici (contrairement au package hybride) : ce
        # serait une écriture sur la base PRINCIPALE (locale, potentiellement
        # injoignable/inexistante pour une installation 100% en ligne, voir
        # config.py) avant même que la bascule ait eu lieu. Le pré-remplissage
        # du lien à la réactivation (blueprints/license/views.py) lit
        # directement current_app.config['SQLALCHEMY_DATABASE_URI'], pas ce
        # Setting — inutile de le dupliquer ici.
        current_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        if database_url != current_uri:
            # license_cache vit dans son propre fichier SQLite (voir
            # models/license_cache.py::__bind_key__), totalement indépendant de
            # la base principale : nul besoin de le "copier" vers la base en
            # ligne avant de basculer, il reste lisible tel quel après le
            # redémarrage, quelle que soit la base Postgres alors active. Il
            # suffit d'enregistrer la bascule ; la base principale (schéma,
            # tables métier) ne sera elle-même créée qu'au prochain démarrage,
            # une fois réellement connectée à cette base en ligne (voir
            # app.py::create_app) — jamais avant, jamais sur la base locale.
            app_config.write_db_override(database_url)
            restart_required = True
        # (sinon : réactivation sur une installation déjà connectée à cette
        # base en ligne — le cache ci-dessus vient d'être mis à jour
        # directement dans la bonne base, rien à basculer.)

    return get_state(), restart_required


def refresh_from_server():
    """Best-effort : appelée au démarrage et périodiquement par le scheduler.
    Ne lève jamais d'exception et ne dégrade jamais le cache existant si le
    serveur est simplement injoignable (hors-ligne)."""
    cache = LicenseCache.get_singleton()
    if cache is None:
        return

    cache.last_verify_attempt_at = datetime.now()

    try:
        data = license_client.verify(cache.installation_token)
    except license_client.LicenseApiUnavailable as exc:
        cache.last_verify_error = str(exc)
        db.session.commit()
        return
    except license_client.LicenseApiRejected as exc:
        cache.status = 'revoked' if exc.error_code == 'TOKEN_REVOKED' else 'expired'
        cache.last_verify_error = str(exc)
        db.session.commit()
        return

    if data.get('status') == 'active':
        expires_at = datetime.fromisoformat(data['expires_at'])
        cache.expires_at = expires_at
        cache.expires_at_hmac = compute_local_hmac(cache.activation_code, expires_at)
        cache.status = 'active'
    else:
        cache.status = 'revoked' if data.get('reason') == 'revoked' else 'expired'

    cache.last_verified_at = datetime.now()
    cache.last_verify_error = None
    db.session.commit()
