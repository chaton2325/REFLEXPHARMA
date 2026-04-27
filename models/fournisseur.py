from extensions import db
from datetime import datetime

class Fournisseur(db.Model):
    __tablename__ = 'fournisseurs'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    site_web = db.Column(db.String(255))
    contact = db.Column(db.String(100))
    prefixe = db.Column(db.String(10), unique=True, nullable=False)
    
    # Nouveaux champs
    coefficient = db.Column(db.Float, nullable=True) # Si None, on prend celui du groupe
    tva = db.Column(db.Float, nullable=True)         # Si None, on prend celui du groupe
    groupe_id = db.Column(db.Integer, db.ForeignKey('groupes_fournisseurs.id'), nullable=True)
    
    # Relation vers les produits
    produits = db.relationship('Produit', backref='fournisseur', lazy=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def effectif_coefficient(self):
        if self.coefficient is not None:
            return self.coefficient
        if self.groupe:
            return self.groupe.coefficient_defaut
        return 1.0 # Valeur par défaut absolue

    @property
    def effectif_tva(self):
        if self.tva is not None:
            return self.tva
        if self.groupe:
            return self.groupe.tva_defaut
        return 20.0 # Valeur par défaut absolue

    def __repr__(self):
        return f'<Fournisseur {self.nom} ({self.prefixe})>'
