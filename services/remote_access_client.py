"""Client HTTP vers /api/v1/remote-access/link (ReflexPharma Admin) : lien
direct vers l'espace REFLEXPHARMA hébergé (voir ReflexPharma-admin
blueprints/pharmacy_app), pour les packages hybride/en ligne. Même
authentification Bearer (installation_token) que services/license_client.py
et services/support_client.py."""
import requests
from flask import current_app

from models.license_cache import LicenseCache
from services.license_client import LicenseApiUnavailable, LicenseApiRejected


def _base_url():
    return (current_app.config.get('LICENSE_ADMIN_API_BASE_URL') or '').rstrip('/')


def _auth_headers():
    cache = LicenseCache.get_singleton()
    if cache is None or not cache.installation_token:
        raise LicenseApiRejected("Aucune installation activée.", 'NOT_ACTIVATED')
    return {'Authorization': f'Bearer {cache.installation_token}'}


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {}


def get_remote_access_link():
    """Retourne {'url': ..., 'readonly': bool}. Lève LicenseApiRejected avec
    un message adapté à l'affichage si le package ne donne pas accès (offline)
    ou LicenseApiUnavailable si le serveur est injoignable."""
    try:
        response = requests.get(f"{_base_url()}/api/v1/remote-access/link",
                                 headers=_auth_headers(), timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', 'Requête refusée.'), data.get('error_code'))
    return data
