from datetime import datetime
from extensions import db

class Inventaire(db.Model):
    __tablename__ = 'inventaires'

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(100), nullable=False)
    statut = db.Column(db.String(30), nullable=False, default='en_cours') # 'planifie', 'en_cours', 'valide', 'annule'
    date_planifiee = db.Column(db.DateTime, nullable=True) # date/heure prevue si statut == 'planifie'

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref=db.backref('inventaires_crees', lazy=True))
    
    validated_at = db.Column(db.DateTime, nullable=True)
    validated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    validated_by = db.relationship('User', foreign_keys=[validated_by_id], backref=db.backref('inventaires_valides', lazy=True))

    def __repr__(self):
        return f'<Inventaire {self.titre} ({self.statut})>'


class InventaireLigne(db.Model):
    __tablename__ = 'inventaire_lignes'

    id = db.Column(db.Integer, primary_key=True)
    inventaire_id = db.Column(db.Integer, db.ForeignKey('inventaires.id', ondelete='CASCADE'), nullable=False)
    inventaire = db.relationship('Inventaire', backref=db.backref('lignes', lazy=True, cascade='all, delete-orphan'))
    
    stock_id = db.Column(db.Integer, db.ForeignKey('stock_entries.id', ondelete='SET NULL'), nullable=True)
    stock = db.relationship('Stock')
    
    produit_id = db.Column(db.Integer, db.ForeignKey('produits.id'), nullable=False)
    produit = db.relationship('Produit')
    
    code_suivi = db.Column(db.String(255), nullable=False)
    numero_bl = db.Column(db.String(120), nullable=False)
    date_peremption = db.Column(db.Date, nullable=False)
    
    # Quantités théoriques (avant inventaire)
    quantite_unites_avant = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_unites_avant = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_sous_unites_avant = db.Column(db.Integer, nullable=False, default=0)
    
    # Quantités constatées (après inventaire)
    quantite_unites_apres = db.Column(db.Integer, nullable=True)
    quantite_sous_unites_apres = db.Column(db.Integer, nullable=True)
    quantite_sous_sous_unites_apres = db.Column(db.Integer, nullable=True)
    
    constate_at = db.Column(db.DateTime, nullable=True)
    constate_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    constate_by = db.relationship('User', foreign_keys=[constate_by_id])
    
    is_scanned = db.Column(db.Boolean, default=False)

    @property
    def total_avant(self):
        return self.quantite_unites_avant + self.quantite_sous_unites_avant + self.quantite_sous_sous_unites_avant

    @property
    def total_apres(self):
        if self.quantite_unites_apres is None and self.quantite_sous_unites_apres is None and self.quantite_sous_sous_unites_apres is None:
            return None
        u = self.quantite_unites_apres or 0
        su = self.quantite_sous_unites_apres or 0
        ssu = self.quantite_sous_sous_unites_apres or 0
        return u + su + ssu

    @property
    def a_decalage(self):
        t_apres = self.total_apres
        if t_apres is None:
            return False
        return self.total_avant != t_apres

    def __repr__(self):
        return f'<InventaireLigne {self.code_suivi} (Avant: {self.total_avant}, Après: {self.total_apres})>'
