from flask import render_template, request, redirect, url_for, flash, current_app

from . import license_bp
from services import license_service
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

        if not code:
            flash("Veuillez saisir un code d'activation.", 'danger')
            return redirect(url_for('license.activate'))

        try:
            license_service.activate_with_code(code, pharmacy_name=pharmacy_name)
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

        flash("Licence activée avec succès. Bienvenue sur ReflexPharma !", 'success')
        return redirect(url_for('auth.login'))

    reactivate_url = f"{current_app.config.get('LICENSE_ADMIN_API_BASE_URL', '').rstrip('/')}/reactiver"
    return render_template('license/activate.html', never_activated=state.never_activated, reactivate_url=reactivate_url)


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
