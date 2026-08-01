from extensions import db
from datetime import datetime

class GroupeFournisseur(db.Model):
    __tablename__ = 'groupes_fournisseurs'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relation vers les fournisseurs
    fournisseurs = db.relationship('Fournisseur', backref='groupe', lazy=True)

    def __repr__(self):
        return f'<GroupeFournisseur {self.nom}>'
