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
import os
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

    Retourne (state, outcome). outcome vaut :
      - 'same' : la base de connexion effective ne change pas (ou Hybride avec
        base locale déjà en place), rien de plus à faire.
      - 'restart_required' : package 'online' déterminé pour la toute première
        activation de cette installation (aucune donnée locale à préserver,
        comportement historique inchangé) — un simple redémarrage suffit,
        config.py::write_db_override ne prend effet qu'au prochain lancement.
      - 'bascule_started' : une bascule ATOMIQUE de base de données (copie
        complète, voir services/db_bascule.py) vient d'être lancée en tâche de
        fond car le package résolu change la base de connexion effective d'une
        installation qui avait déjà des données. LicenseCache.package et la
        base de connexion ne changent qu'une fois cette bascule terminée avec
        succès (voir license.bascule_status) — jamais avant, pour qu'une
        coupure de courant en plein transfert laisse l'installation exactement
        comme avant."""
    import config as app_config
    from models.setting import Setting
    from services import db_bascule

    cache_existed_before = LicenseCache.get_singleton() is not None

    data = license_client.activate(activation_code, pharmacy_name=pharmacy_name,
                                    online_database_url=online_database_url)

    expires_at = datetime.fromisoformat(data['expires_at'])
    now = datetime.now()
    package = data.get('package', 'offline')
    database_url = data.get('database_url')

    # Base sur laquelle l'app tournera effectivement pour le package résolu :
    # toujours DATABASE_LOCAL_URL pour offline/hybrid (l'Hybride tourne
    # toujours sur la base locale, la base en ligne n'étant qu'un miroir
    # périodique manuel, voir services/db_sync.py), sinon l'URL en ligne
    # attribuée par le serveur.
    current_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
    local_uri = os.getenv('DATABASE_LOCAL_URL')
    new_uri = database_url if package == 'online' else local_uri

    # Une bascule (copie complète) n'est nécessaire que si la base de connexion
    # change réellement ET qu'il existait déjà une installation active — sur
    # la toute première activation (cache_existed_before == False), il n'y a
    # encore aucune donnée locale à préserver, voir outcome 'restart_required'
    # ci-dessous. Couvre aussi bien offline/hybrid -> online, online ->
    # offline/hybrid, que online -> un autre online (migration d'hébergement).
    needs_bascule = bool(
        cache_existed_before and new_uri and current_uri and new_uri != current_uri
    )

    cache = LicenseCache.get_singleton()
    if cache is None:
        cache = LicenseCache()
        db.session.add(cache)

    cache.activation_code = activation_code
    cache.installation_token = data['installation_token']
    cache.pharmacy_id_remote = data.get('pharmacy_id')
    cache.expires_at = expires_at
    cache.expires_at_hmac = compute_local_hmac(activation_code, expires_at)
    cache.status = 'active'
    cache.last_verified_at = now
    cache.last_verify_attempt_at = now
    cache.last_verify_error = None
    cache.clock_high_water_mark = now
    if not needs_bascule:
        cache.package = package

    db.session.commit()

    outcome = 'same'
    if needs_bascule:
        direction = 'to_local' if new_uri == local_uri else 'to_online'
        db_bascule.start(
            current_app._get_current_object(), direction=direction,
            target_package=package, source_url=current_uri, target_url=new_uri,
            # Pertinent uniquement si package == 'hybrid' (ex: online -> hybride) :
            # la base fraîchement attribuée pour CE package, que ni source_url
            # (l'ancienne base en ligne qu'on quitte) ni target_url (la base
            # locale) ne portent -- voir models/db_bascule.py::hybrid_online_url.
            hybrid_online_url=database_url if package == 'hybrid' else None,
        )
        outcome = 'bascule_started'
    elif package == 'hybrid' and database_url:
        Setting.set_value('online_database_url', database_url,
                           "Base en ligne du package Hybride (synchronisation manuelle, voir Paramètres)")
    elif package == 'online' and database_url and database_url != current_uri:
        # needs_bascule est False ici uniquement parce que cache_existed_before
        # est False (toute première activation) : aucune donnée locale à
        # préserver, un redémarrage simple suffit comme avant ce changement.
        app_config.write_db_override(database_url)
        outcome = 'restart_required'

    return get_state(), outcome


def redeem_renewal_code(renewal_code):
    """Finalise un renouvellement payé (voir ReflexPharma Admin
    models/renewal_code.py) : contrairement à activate_with_code(), aucun
    nouveau installation_token n'est émis, package/base restent ceux déjà en
    place — on ne fait que ré-écrire expires_at/HMAC/status localement à
    partir de la réponse du serveur, seule source faisant autorité.
    Lève LicenseApiUnavailable/LicenseApiRejected comme activate_with_code."""
    cache = LicenseCache.get_singleton()
    if cache is None:
        raise license_client.LicenseApiRejected(
            "Aucune installation active : utilisez d'abord un code d'activation.", 'NOT_ACTIVATED'
        )

    data = license_client.redeem_renewal(renewal_code)

    expires_at = datetime.fromisoformat(data['expires_at'])
    cache.expires_at = expires_at
    cache.expires_at_hmac = compute_local_hmac(cache.activation_code, expires_at)
    cache.status = 'active'
    cache.last_verified_at = datetime.now()
    cache.last_verify_attempt_at = datetime.now()
    cache.last_verify_error = None
    db.session.commit()

    return get_state()


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
