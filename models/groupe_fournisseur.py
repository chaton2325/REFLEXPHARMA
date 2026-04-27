from extensions import db
from datetime import datetime

class GroupeFournisseur(db.Model):
    __tablename__ = 'groupes_fournisseurs'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    coefficient_defaut = db.Column(db.Float, default=1.0)
    tva_defaut = db.Column(db.Float, default=20.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relation vers les fournisseurs
    fournisseurs = db.relationship('Fournisseur', backref='groupe', lazy=True)

    def __repr__(self):
        return f'<GroupeFournisseur {self.nom}>'
