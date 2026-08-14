from datetime import datetime
from extensions import db

class RaisonAnnulationVente(db.Model):
    __tablename__ = 'raisons_annulation_vente'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f'<RaisonAnnulationVente {self.nom}>'
