from flask import Blueprint, request, redirect, url_for

license_bp = Blueprint('license', __name__)

# Ces endpoints restent joignables même sans licence valide : la page d'activation
# elle-même, la page de blocage, les fichiers statiques, le téléchargement du
# certificat CA (nécessaire pour configurer l'accès réseau avant même d'avoir une
# licence, ex: premier réglage du serveur), et les deux endpoints de réactivation
# rapide (doivent fonctionner justement PARCE QUE la licence est invalide/expirée,
# voir views.py::reactivate_redirect / redeem_renewal). Ne dispense PAS du test de
# bascule ci-dessous : voir BASCULE_EXEMPT_ENDPOINTS pour ça.
EXEMPT_ENDPOINTS = {
    'license.activate', 'license.locked', 'static', 'download_ca_cert',
    'license.reactivate_redirect', 'license.redeem_renewal',
}

# Seuls ces endpoints échappent au blocage pendant une bascule (voir
# services/db_bascule.py) : sa page de statut et ses actions retry/cancel,
# joignables SANS connexion (la base principale — et donc la table des
# utilisateurs — peut être en plein transfert). Volontairement PAS
# 'license.activate' : un nouveau code d'activation ne sert à rien pour
# reprendre une bascule (elle a déjà toutes les infos nécessaires en local, voir
# services/db_bascule.py::retry) et les codes étant à usage unique, resaisir le
# même échouerait côté serveur (déjà consommé) — d'où la confusion possible si
# cette page restait accessible pendant une bascule en cours/en échec.
BASCULE_EXEMPT_ENDPOINTS = {
    'license.bascule_status', 'license.bascule_retry', 'license.bascule_cancel', 'static',
}


@license_bp.before_app_request
def check_license():
    """Bloque toute route de l'application (y compris la page de connexion ET la
    page d'activation) tant qu'une bascule de base de données (changement de
    package, voir services/db_bascule.py) est en cours/en attente/en erreur —
    pendant tout ce laps de temps, l'app est volontairement inutilisable (y
    compris pour un admin déjà connecté, et y compris pour ressaisir un code)
    pour garantir la cohérence des données transférées ET pour que l'unique
    action disponible reste la page de statut (retry/cancel), voir le docstring
    de services/db_bascule.py. Bloque aussi toute route tant qu'aucune licence
    valide n'est en cache localement. Lectures 100% locales (aucun appel
    réseau) : voir services/license_service.py::get_state() et
    services/db_bascule.py::get_status()."""
    if request.endpoint is None:
        return

    if request.endpoint not in BASCULE_EXEMPT_ENDPOINTS:
        from services import db_bascule
        bascule_status = db_bascule.get_status()
        if bascule_status is not None and bascule_status['status'] != 'done':
            return redirect(url_for('license.bascule_status'))

    if request.endpoint in EXEMPT_ENDPOINTS:
        return

    from services import license_service
    state = license_service.get_state()
    if not state.is_valid():
        target = 'license.activate' if state.never_activated else 'license.locked'
        return redirect(url_for(target))


from . import views
