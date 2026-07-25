from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user

from . import license_bp
from services import license_service
from services import license_client
from services.license_client import LicenseApiUnavailable, LicenseApiRejected

REASON_LABELS = {
    'expired': "Votre abonnement ReflexPharma a expiré.",
    'revoked': "Votre licence ReflexPharma a été révoquée.",
    'tampered': "Une anomalie a été détectée sur les données de licence de cette installation.",
    'clock_rollback': "L'horloge de cet ordinateur semble avoir été modifiée. Une reconnexion à internet est nécessaire pour revérifier votre licence.",
}


@license_bp.route('/activate', methods=['GET', 'POST'])
def activate():
    state = license_service.get_state()
    if state.is_valid():
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = (request.form.get('activation_code') or '').strip().upper()
        pharmacy_name = (request.form.get('pharmacy_name') or '').strip() or None
        online_database_url = (request.form.get('online_database_url') or '').strip() or None

        if not code:
            flash("Veuillez saisir un code d'activation.", 'danger')
            return redirect(url_for('license.activate'))

        try:
            _, restart_required = license_service.activate_with_code(
                code, pharmacy_name=pharmacy_name, online_database_url=online_database_url
            )
        except LicenseApiUnavailable:
            flash(
                "Connexion Internet requise : l'activation d'une licence nécessite un accès Internet pour "
                "vérifier votre code auprès du serveur ReflexPharma. Cet accès n'est nécessaire que pour "
                "l'activation — une fois activée, l'application fonctionne hors ligne jusqu'à la date "
                "d'expiration. Vérifiez votre connexion et réessayez.",
                'danger'
            )
            return redirect(url_for('license.activate'))
        except LicenseApiRejected as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('license.activate'))

        if restart_required:
            flash(
                "Licence activée avec succès. Votre abonnement utilise une base de données 100% en ligne : "
                "fermez complètement ReflexPharma puis relancez-le pour basculer dessus.",
                'success'
            )
        else:
            # Le package vient d'être déterminé pour la première fois (ou l'app
            # était déjà connectée à la bonne base en ligne) : c'est le tout
            # premier moment sûr où la base principale peut être sollicitée
            # (voir app.py::create_app, qui n'appelle pas ensure_database_schema
            # tant qu'aucune licence n'a jamais été activée).
            from app import ensure_database_schema
            ensure_database_schema(current_app._get_current_object())

            from services.bootstrap import ensure_bootstrap_admin_user
            ensure_bootstrap_admin_user(current_app._get_current_object())

            flash("Licence activée avec succès. Bienvenue sur ReflexPharma !", 'success')
        return redirect(url_for('auth.login'))

    reactivate_url = f"{current_app.config.get('LICENSE_ADMIN_API_BASE_URL', '').rstrip('/')}/reactiver"
    # L'installation garde la trace du dernier package connu même une fois la
    # licence expirée/révoquée (state.cache n'est jamais supprimé, seul son
    # statut change) : sert à ne pas redemander le lien de base de données à la
    # réactivation d'un package déjà configuré — ReflexPharma Admin l'exige
    # désormais obligatoirement (services/licenses.py::activate_license), donc
    # ce pré-remplissage automatique est indispensable pour ne jamais bloquer
    # une réactivation légitime.
    previous_package = state.cache.package if state.cache else None
    known_database_url = None
    if previous_package == 'hybrid':
        from models.setting import Setting
        known_database_url = Setting.get_value('online_database_url')
    elif previous_package == 'online':
        # Pour le package en ligne, l'app EST déjà connectée à la bonne base :
        # c'est la source la plus fiable (pas de dépendance à un Setting qui
        # pourrait ne pas encore exister juste après une bascule, voir
        # services/license_service.py::activate_with_code).
        known_database_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')

    return render_template(
        'license/activate.html', never_activated=state.never_activated,
        reactivate_url=reactivate_url, previous_package=previous_package,
        known_database_url=known_database_url,
    )


@license_bp.route('/reactivate-redirect')
def reactivate_redirect():
    """Bouton "Réactiver mon abonnement" (settings.html et locked.html) : cette
    installation est déjà connue (installation_token existant), donc pas besoin
    de repasser par l'email/OTP ni de ressaisir un code — on échange le token
    contre une clé de réactivation courte durée côté serveur (jamais exposée au
    navigateur, voir services/license_client.py::prepare_reactivation) puis on
    redirige vers la page publique déjà pré-remplie.

    En cas d'échec (pas de licence connue, réseau injoignable, licence
    révoquée) : repli sur la page générique /reactiver, identique au bouton
    "Réactiver un autre abonnement"."""
    generic_url = f"{current_app.config.get('LICENSE_ADMIN_API_BASE_URL', '').rstrip('/')}/reactiver"

    state = license_service.get_state()
    if state.cache is None or not state.cache.installation_token:
        return redirect(generic_url)

    try:
        data = license_client.prepare_reactivation(state.cache.installation_token)
    except (LicenseApiUnavailable, LicenseApiRejected) as exc:
        flash(f"Réactivation rapide indisponible ({exc}). Utilisez \"Réactiver un autre abonnement\" ci-dessous "
              f"ou réessayez dans un instant.", 'warning')
        return redirect(generic_url)

    return redirect(f"{generic_url}?rk={data['reactivation_key']}")


@license_bp.route('/redeem-renewal', methods=['POST'])
def redeem_renewal():
    """Saisie du code de réactivation reçu par email après un paiement de
    réactivation rapide (voir ReflexPharma Admin models/renewal_code.py) —
    depuis Paramètres (licence encore valide, renouvellement anticipé) ou
    depuis l'écran de blocage (licence déjà expirée). 100% "pull" : aucun
    webhook, aucune détection automatique, le renouvellement n'a lieu qu'à
    cette saisie explicite."""
    code = (request.form.get('renewal_code') or '').strip().upper()
    redirect_target = url_for('admin.app_settings') if current_user.is_authenticated else url_for('license.locked')

    if not code:
        flash("Veuillez saisir un code de réactivation.", 'danger')
        return redirect(redirect_target)

    try:
        license_service.redeem_renewal_code(code)
    except LicenseApiUnavailable:
        flash(
            "Connexion Internet requise pour vérifier ce code auprès du serveur ReflexPharma. "
            "Vérifiez votre connexion et réessayez.",
            'danger'
        )
        return redirect(redirect_target)
    except LicenseApiRejected as exc:
        flash(str(exc), 'danger')
        return redirect(redirect_target)

    flash("Abonnement réactivé avec succès.", 'success')
    return redirect(url_for('auth.login') if not current_user.is_authenticated else url_for('admin.app_settings'))


@license_bp.route('/locked')
def locked():
    state = license_service.get_state()
    if state.is_valid():
        return redirect(url_for('auth.login'))
    if state.never_activated:
        return redirect(url_for('license.activate'))

    reactivate_url = f"{current_app.config.get('LICENSE_ADMIN_API_BASE_URL', '').rstrip('/')}/reactiver"

    return render_template(
        'license/locked.html',
        reason=state.reason,
        reason_label=REASON_LABELS.get(state.reason, "Votre licence ReflexPharma n'est plus valide."),
        cache=state.cache,
        reactivate_url=reactivate_url,
    )
