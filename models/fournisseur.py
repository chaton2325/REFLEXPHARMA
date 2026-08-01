from extensions import db
from datetime import datetime

class Fournisseur(db.Model):
    __tablename__ = 'fournisseurs'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    site_web = db.Column(db.String(255))
    contact = db.Column(db.String(100))
    prefixe = db.Column(db.String(10), unique=True, nullable=False)

    groupe_id = db.Column(db.Integer, db.ForeignKey('groupes_fournisseurs.id'), nullable=True)
    
    # Relation vers les produits
    produits = db.relationship('Produit', backref='fournisseur', lazy=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<Fournisseur {self.nom} ({self.prefixe})>'
