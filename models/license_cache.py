from datetime import datetime
from extensions import db


class LicenseCache(db.Model):
    """Copie locale de l'état de licence de cette pharmacie, utilisée pour continuer
    à fonctionner hors-ligne jusqu'à expires_at (voir services/license_service.py).

    Une seule ligne logique par installation. expires_at_hmac permet de détecter une
    modification frauduleuse directe de expires_at en base locale (voir
    services/license_service.py::compute_local_hmac).

    Vit dans son propre fichier SQLite (voir config.py::SQLALCHEMY_BINDS),
    complètement indépendant de la base Postgres principale (locale ou en
    ligne) : c'est justement CE modèle qui permet de savoir quel package est
    actif, donc il doit rester interrogeable même quand aucun Postgres n'a
    encore été configuré/n'est joignable — avant la toute première activation
    notamment (voir app.py::create_app, appelé inconditionnellement, alors que
    la base principale ne l'est que conditionnellement)."""
    __bind_key__ = 'license'
    __tablename__ = 'license_cache'

    id = db.Column(db.Integer, primary_key=True)
    activation_code = db.Column(db.String(30), nullable=False)
    installation_token = db.Column(db.String(255), nullable=False)
    pharmacy_id_remote = db.Column(db.Integer)

    # offline (hors ligne total), hybrid (local + synchronisation manuelle vers une
    # base en ligne), online (100% en ligne, voir config.py::_resolve_database_uri
    # pour la bascule de connexion). Détermine ce qui s'affiche dans Paramètres.
    package = db.Column(db.String(20), nullable=False, default='offline')

    expires_at = db.Column(db.DateTime)
    expires_at_hmac = db.Column(db.String(64))

    status = db.Column(db.String(20), nullable=False, default='active')  # active, expired, revoked, tampered

    last_verified_at = db.Column(db.DateTime)
    last_verify_attempt_at = db.Column(db.DateTime)
    last_verify_error = db.Column(db.Text)

    # Plus grand horodatage système jamais observé localement : sert à détecter un
    # recul manuel de l'horloge visant à prolonger artificiellement la période
    # d'utilisation hors-ligne (voir services/license_service.py).
    clock_high_water_mark = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def get_singleton():
        return LicenseCache.query.order_by(LicenseCache.id.asc()).first()

    def __repr__(self):
        return f'<LicenseCache {self.activation_code} status={self.status} expires_at={self.expires_at}>'
