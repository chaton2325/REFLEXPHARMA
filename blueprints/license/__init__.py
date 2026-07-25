from flask import Blueprint, request, redirect, url_for

license_bp = Blueprint('license', __name__)

# Ces endpoints restent joignables même sans licence valide : la page d'activation
# elle-même, la page de blocage, les fichiers statiques, le téléchargement du
# certificat CA (nécessaire pour configurer l'accès réseau avant même d'avoir une
# licence, ex: premier réglage du serveur), et les deux endpoints de réactivation
# rapide (doivent fonctionner justement PARCE QUE la licence est invalide/expirée,
# voir views.py::reactivate_redirect / redeem_renewal).
EXEMPT_ENDPOINTS = {
    'license.activate', 'license.locked', 'static', 'download_ca_cert',
    'license.reactivate_redirect', 'license.redeem_renewal',
}


@license_bp.before_app_request
def check_license():
    """Bloque toute route de l'application (y compris la page de connexion) tant
    qu'aucune licence valide n'est en cache localement. Lecture 100% locale (aucun
    appel réseau) : voir services/license_service.py::get_state()."""
    if request.endpoint is None or request.endpoint in EXEMPT_ENDPOINTS:
        return

    from services import license_service
    state = license_service.get_state()
    if not state.is_valid():
        target = 'license.activate' if state.never_activated else 'license.locked'
        return redirect(url_for(target))


from . import views
