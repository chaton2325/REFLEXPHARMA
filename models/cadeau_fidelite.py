from extensions import db
from datetime import datetime

class CadeauFidelite(db.Model):
    __tablename__ = 'cadeaux_fidelite'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    points_requis = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    actif = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<CadeauFidelite {self.nom} ({self.points_requis} pts)>'
