from extensions import db
from datetime import datetime

class Famille(db.Model):
    __tablename__ = 'familles'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    produits = db.relationship('Produit', backref='famille', lazy=True)

    def __repr__(self):
        return f'<Famille {self.nom}>'
