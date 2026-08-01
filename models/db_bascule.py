from datetime import datetime
from extensions import db


class DbBascule(db.Model):
    """État d'une bascule de base de données en cours/à reprendre, déclenchée par
    un changement de package de licence qui change la base de connexion effective
    (voir services/db_bascule.py). Une seule ligne logique par installation.

    Vit dans le fichier SQLite dédié à la licence (voir config.py::LICENSE_DB_PATH
    et models/license_cache.py), complètement indépendant de la base Postgres
    principale (locale ou en ligne) : c'est justement CE modèle qui doit rester
    lisible/écrivable pendant qu'une bascule est en cours ou vient d'échouer,
    y compris quand ni l'ancienne ni la nouvelle base Postgres ne sont
    utilisables (coupure réseau vers la base en ligne, base locale pas encore
    créée...). C'est ce qui permet la reprise automatique au redémarrage sans
    dépendre d'une connexion admin (voir app.py::create_app)."""
    __bind_key__ = 'license'
    __tablename__ = 'db_bascule'

    id = db.Column(db.Integer, primary_key=True)

    # to_local (en ligne -> locale) ou to_online (locale -> en ligne).
    direction = db.Column(db.String(20), nullable=False)
    source_url = db.Column(db.Text, nullable=False)
    target_url = db.Column(db.Text, nullable=False)
    # Package à appliquer à LicenseCache.package une fois la bascule terminée
    # (offline, hybrid ou online) — voir services/db_bascule.py::run_pending.
    target_package = db.Column(db.String(20), nullable=False)

    # URL de la base en ligne à retenir pour Setting['online_database_url'] une
    # fois la bascule terminée, UNIQUEMENT quand target_package == 'hybrid' ET
    # que la bascule part d'un package 'online' (direction 'to_local') : dans ce
    # cas précis, ni source_url (l'ancienne base en ligne qu'on quitte) ni
    # target_url (la base locale) ne portent la bonne information -- c'est la
    # base NOUVELLEMENT attribuée par le serveur pour le package hybride visé,
    # distincte des deux (voir services/license_service.py::activate_with_code).
    # NULL dans tous les autres cas, où elle ne joue aucun rôle.
    hybrid_online_url = db.Column(db.Text, nullable=True)

    # pending -> dumping -> restoring -> restored -> done, avec branche
    # possible vers error à chaque étape dump/creation/restore (voir
    # services/db_bascule.py pour le détail de la machine à états).
    status = db.Column(db.String(20), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text)

    started_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    finished_at = db.Column(db.DateTime)

    @staticmethod
    def get_singleton():
        return DbBascule.query.order_by(DbBascule.id.asc()).first()

    def __repr__(self):
        return f'<DbBascule {self.direction} status={self.status} attempts={self.attempts}>'
