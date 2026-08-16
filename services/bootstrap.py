"""Création automatique du tout premier compte administrateur si la base
actuellement connectée n'a encore aucun utilisateur — couvre les 3 packages
sans distinction : ce module regarde l'état réel de la base au démarrage,
quelle qu'elle soit (locale pour hors ligne/hybride, ou base en ligne
fraîchement créée après bascule pour le package 'online', voir config.py).

Avant ce module, une installation neuve n'avait aucun moyen de se connecter
sans qu'un humain lance manuellement seed.py (mot de passe fixe 'admin123')."""
import secrets
import threading

import config as app_config
from extensions import db
from models.user import User
from models.license_cache import LicenseCache

ADMIN_USERNAME = 'admin'
ADMIN_EMAIL_PLACEHOLDER = 'admin@tsaripharm.local'


def ensure_bootstrap_admin_user(app):
    """Idempotent (ne fait rien si un utilisateur existe déjà, quel qu'il
    soit) : sans danger à appeler à chaque démarrage. Le mot de passe généré
    est écrit dans instance/first_admin_credentials.json — affiché sur la page
    de connexion tant que ce compte n'a jamais servi, voir
    blueprints/auth/views.py — ET envoyé par email via ReflexPharma Admin
    (best-effort, en tâche de fond, ne bloque jamais le démarrage : cette
    installation n'a pas encore de SMTP configuré à ce stade)."""
    with app.app_context():
        # LicenseCache (SQLite, voir models/license_cache.py::__bind_key__) est
        # TOUJOURS interrogeable, contrairement à `User` (base principale,
        # Postgres locale ou en ligne) qui peut ne pas encore être connue/
        # joignable tant qu'aucune licence n'a jamais été activée (package
        # 'online' notamment, voir app.py::create_app) : ce check doit donc
        # passer en premier, sous peine de faire planter le démarrage sur une
        # installation neuve.
        cache = LicenseCache.get_singleton()
        if cache is None or not cache.installation_token:
            return  # pas encore activé : rien à amorcer pour l'instant

        if User.query.first() is not None:
            return

        password = secrets.token_urlsafe(12)
        admin_user = User(
            nom='Administrateur', prenom='TsariPharm',
            email=ADMIN_EMAIL_PLACEHOLDER, username=ADMIN_USERNAME,
            role='superadmin', is_active=True,
        )
        admin_user.set_password(password)
        db.session.add(admin_user)
        db.session.commit()

        app_config.write_first_login_credentials(ADMIN_USERNAME, password)

        def notify():
            with app.app_context():
                try:
                    from services import license_client
                    license_client.notify_credentials(cache.installation_token, ADMIN_USERNAME, password)
                except Exception:
                    pass  # best-effort : le fichier local reste le filet de sécurité principal

        threading.Thread(target=notify, daemon=True).start()
