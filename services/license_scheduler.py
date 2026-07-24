"""Vérification périodique de la licence en arrière-plan (APScheduler), pour
resynchroniser avec le serveur dès que la connexion revient sans jamais bloquer
le démarrage ni l'utilisation de l'app. Démarré uniquement depuis le bloc
`if __name__ == '__main__':` de app.py/run.py (voir garde anti-double-démarrage
sous le reloader Flask à cet endroit), jamais depuis create_app()."""
import threading
from apscheduler.schedulers.background import BackgroundScheduler

from services import license_service

_scheduler = None


def start_license_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return

    interval_minutes = app.config.get('LICENSE_CHECK_INTERVAL_MINUTES', 60)

    def job():
        with app.app_context():
            license_service.refresh_from_server()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(job, 'interval', minutes=interval_minutes, id='license_refresh')
    scheduler.start()
    _scheduler = scheduler

    # Un premier check est tenté immédiatement en tâche de fond (best-effort, ne
    # bloque pas le démarrage) pour resynchroniser plus vite après une coupure,
    # sans attendre le premier tick de l'intervalle.
    threading.Thread(target=job, daemon=True).start()
