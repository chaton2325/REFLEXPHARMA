from extensions import db
from datetime import datetime

class Poste(db.Model):
    __tablename__ = 'postes'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Poste {self.nom}>'
