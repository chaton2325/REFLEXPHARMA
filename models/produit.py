from extensions import db
from datetime import datetime

class Produit(db.Model):
    __tablename__ = 'produits'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    code_produit = db.Column(db.String(50), unique=True, nullable=False)
    
    # Relations
    fournisseur_id = db.Column(db.Integer, db.ForeignKey('fournisseurs.id'), nullable=False)
    rayon_id = db.Column(db.Integer, db.ForeignKey('rayons.id'))
    famille_id = db.Column(db.Integer, db.ForeignKey('familles.id'))
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'))
    
    # Conditionnement: 1, 2 ou 3
    conditionnement = db.Column(db.Integer, default=1)
    
    # Prix
    prix_unite = db.Column(db.Float, default=0.0)
    prix_sous_unite = db.Column(db.Float, nullable=True) # Utilise si conditionnement >= 2
    prix_sous_sous_unite = db.Column(db.Float, nullable=True) # Utilise si conditionnement == 3
    
    # Parametres financiers (peuvent surcharger ceux du fournisseur)
    coefficient = db.Column(db.Float, nullable=True)
    tva = db.Column(db.Float, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def effectif_coefficient(self):
        if self.coefficient is not None:
            return self.coefficient
        return self.fournisseur.effectif_coefficient if self.fournisseur else 1.0

    @property
    def effectif_tva(self):
        if self.tva is not None:
            return self.tva
        return self.fournisseur.effectif_tva if self.fournisseur else 20.0

    def __repr__(self):
        return f'<Produit {self.nom} ({self.code_produit})>'
