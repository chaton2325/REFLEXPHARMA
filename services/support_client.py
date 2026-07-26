"""Client HTTP vers la messagerie support de ReflexPharma Admin
(POST/GET /api/v1/support/... côté serveur, voir ReflexPharma-admin
blueprints/api/views.py et services/support.py), même forme que
services/license_client.py : authentification Bearer avec le
installation_token déjà émis à l'activation (models/license_cache.py), aucune
nouvelle identification à créer. Nécessite une connexion Internet -- pas de
cache local, contrairement à l'état de licence (voir license_service.py)."""
import requests
from flask import current_app

from models.license_cache import LicenseCache
from services.license_client import LicenseApiUnavailable, LicenseApiRejected


def _base_url():
    return (current_app.config.get('LICENSE_ADMIN_API_BASE_URL') or '').rstrip('/')


def _auth_headers():
    cache = LicenseCache.get_singleton()
    if cache is None or not cache.installation_token:
        raise LicenseApiRejected("Aucune installation activée : impossible d'utiliser le support.", 'NOT_ACTIVATED')
    return {'Authorization': f'Bearer {cache.installation_token}'}


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {}


def list_messages(after_id=None):
    """Retourne {'messages': [...], 'read_up_to': N} -- read_up_to est le plus
    grand id des messages envoyés par CETTE pharmacie déjà lus côté staff,
    utilisé pour mettre à jour la coche de lecture de messages déjà affichés
    à l'écran (voir templates/admin/support_chat.html)."""
    params = {'after_id': after_id} if after_id else {}
    try:
        response = requests.get(f"{_base_url()}/api/v1/support/messages", params=params,
                                 headers=_auth_headers(), timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', 'Requête refusée.'), data.get('error_code'))
    return {'messages': data.get('messages', []), 'read_up_to': data.get('read_up_to', 0)}


def send_text(body):
    try:
        response = requests.post(f"{_base_url()}/api/v1/support/messages", json={'body': body},
                                  headers=_auth_headers(), timeout=10)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', "Échec de l'envoi."), data.get('error_code'))
    return data.get('message')


def send_image(file_storage):
    """file_storage : werkzeug.datastructures.FileStorage reçu de
    request.files['image'] côté blueprints/admin/views.py."""
    try:
        files = {'image': (file_storage.filename, file_storage.stream, file_storage.mimetype)}
        response = requests.post(f"{_base_url()}/api/v1/support/messages/image", files=files,
                                  headers=_auth_headers(), timeout=30)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    data = _safe_json(response)
    if response.status_code >= 500:
        raise LicenseApiUnavailable(f"Erreur serveur ({response.status_code})")
    if response.status_code >= 400:
        raise LicenseApiRejected(data.get('message', "Échec de l'envoi de l'image."), data.get('error_code'))
    return data.get('message')


def get_image(message_id):
    """Relaie l'image depuis ReflexPharma Admin (le navigateur n'a jamais
    besoin de connaître l'URL de l'API ni le installation_token). Retourne
    (contenu binaire, content-type)."""
    try:
        response = requests.get(f"{_base_url()}/api/v1/support/messages/{message_id}/image",
                                 headers=_auth_headers(), timeout=15)
    except requests.RequestException as exc:
        raise LicenseApiUnavailable(str(exc)) from exc

    if response.status_code == 404:
        raise LicenseApiRejected("Image introuvable.", 'NOT_FOUND')
    if response.status_code >= 400:
        raise LicenseApiRejected("Échec de récupération de l'image.", None)
    return response.content, response.headers.get('Content-Type', 'application/octet-stream')


def mark_read():
    try:
        requests.post(f"{_base_url()}/api/v1/support/read", headers=_auth_headers(), timeout=10)
    except requests.RequestException:
        pass  # best-effort, ne bloque jamais l'affichage du fil


def unread_count():
    """Utilisé pour le badge non-lus de la barre latérale (voir
    templates/base.html) : best-effort, ne lève jamais -- une erreur réseau ou
    une installation pas encore activée se traduit juste par un badge absent,
    jamais par une page cassée (appelé depuis un sondage JS de fond sur toutes
    les pages)."""
    try:
        response = requests.get(f"{_base_url()}/api/v1/support/unread-count",
                                 headers=_auth_headers(), timeout=8)
    except (requests.RequestException, LicenseApiRejected):
        return 0
    if response.status_code != 200:
        return 0
    return _safe_json(response).get('count', 0)
