"""Client HTTP vers l'API de licence de ReflexPharma Admin
(POST /api/v1/licenses/activate et /verify).

Toutes les erreurs réseau/HTTP sont normalisées en LicenseApiUnavailable (pas de
réseau, serveur injoignable/en erreur) ou LicenseApiRejected (le serveur a répondu
mais refuse la demande : code inconnu, révoqué...), pour que les appelants
puissent distinguer "pas de connexion, on garde le cache local" de "le serveur dit
explicitement non"."""
import requests
from flask import current_app


class LicenseApiUnavailable(Exception):
    """L'API n'a pas pu être jointe (pas de réseau, timeout, erreur serveur 5xx)."""


class LicenseApiRejected(Exception):
    """L'API a répondu mais refuse la demande (code invalide, révoqué, token invalide...)."""

    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


def _base_url():
    return (current_app.config.get('LICENSE_ADMIN_API_BASE_URL') or '').rstrip('/')


def activate(activation_code, pharmacy_name=None, app_version=None, online_database_url=None):
    payload = {'activation_code': activation_code}
    if pharmacy_name:
        payload['pharmacy_name'] = pharmacy_name
    if app_version:
        payload['app_version'] = app_version
    if online_database_url:
        # Simple confort utilisateur (pré-rempli depuis l'email reçu) : le serveur
        # ne s'en sert jamais pour déterminer la vraie base, voir services/licenses.py
        # côté ReflexPharma Admin — la réponse ci-dessous (data['database_url']) est
        # la seule source faisant autorité.
        payload['online_database_url'] = online_database_url

    try:
        response = requests.post(f"{_base_url()}/api/v1/licenses/activate", json=payload, timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', 'Code d\'activation refusé.'), data.get('error_code'))
    return data


def verify(installation_token, app_version=None):
    payload = {}
    if app_version:
        payload['app_version'] = app_version
    headers = {'Authorization': f'Bearer {installation_token}'}

    try:
        response = requests.post(f"{_base_url()}/api/v1/licenses/verify", json=payload, headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', 'Vérification refusée.'), data.get('error_code'))
    return data


def prepare_reactivation(installation_token, app_version=None):
    """Échange l'installation_token (jamais exposé au navigateur) contre une clé
    de réactivation courte durée/usage unique (voir ReflexPharma Admin
    models/reactivation_token.py), pour rediriger l'utilisateur vers /reactiver
    sans lui redemander ni email/OTP ni code d'activation — voir
    blueprints/license/views.py::reactivate_redirect."""
    payload = {}
    if app_version:
        payload['app_version'] = app_version
    headers = {'Authorization': f'Bearer {installation_token}'}

    try:
        response = requests.post(f"{_base_url()}/api/v1/licenses/prepare-reactivation", json=payload, headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', 'Réactivation refusée.'), data.get('error_code'))
    return data


def redeem_renewal(renewal_code, app_version=None):
    """Le code EST le secret (même modèle que activate(), pas de Bearer requis) :
    finalise un renouvellement payé (voir ReflexPharma Admin
    models/renewal_code.py). 100% "pull" — aucun webhook, aucune détection
    automatique : c'est cet appel, déclenché par la saisie du code dans
    l'app, qui étend réellement expires_at côté serveur central."""
    payload = {'renewal_code': renewal_code}
    if app_version:
        payload['app_version'] = app_version

    try:
        response = requests.post(f"{_base_url()}/api/v1/licenses/redeem-renewal", json=payload, timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', 'Code de réactivation refusé.'), data.get('error_code'))
    return data


def notify_credentials(installation_token, username, password, app_version=None):
    """Demande à ReflexPharma Admin d'envoyer par email les identifiants du
    premier compte admin local (voir services/bootstrap.py) — cette
    installation n'a pas encore de SMTP configuré à ce stade."""
    payload = {'username': username, 'password': password}
    if app_version:
        payload['app_version'] = app_version
    headers = {'Authorization': f'Bearer {installation_token}'}

    try:
        response = requests.post(f"{_base_url()}/api/v1/licenses/notify-credentials", json=payload, headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', "Échec de l'envoi des identifiants."), data.get('error_code'))
    return data


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {}
