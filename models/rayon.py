from extensions import db
from datetime import datetime

class Rayon(db.Model):
    __tablename__ = 'rayons'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Points de fidelite par unite achetee pour les produits de ce rayon.
    # NULL = pas de regle a ce niveau (le fallback continue vers section).
    points_fidelite = db.Column(db.Integer, nullable=True)

    produits = db.relationship('Produit', backref='rayon', lazy=True)

    def __repr__(self):
        return f'<Rayon {self.nom}>'
