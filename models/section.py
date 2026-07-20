from extensions import db
from datetime import datetime

class Section(db.Model):
    __tablename__ = 'sections'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Points de fidelite par unite achetee pour les produits de cette section.
    # NULL = pas de regle a ce niveau (dernier maillon du fallback, sinon 0).
    points_fidelite = db.Column(db.Integer, nullable=True)

    produits = db.relationship('Produit', backref='section', lazy=True)

    def __repr__(self):
        return f'<Section {self.nom}>'
