from datetime import datetime

from extensions import db


class Stock(db.Model):
    __tablename__ = 'stocks'

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produits.id'), nullable=False, unique=True)
    quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    produit = db.relationship(
        'Produit',
        backref=db.backref('stock', uselist=False, cascade='all, delete-orphan', single_parent=True)
    )

    @staticmethod
    def _safe_price(value):
        return float(value or 0)

    @property
    def prix_ht_total(self):
        return (
            self.quantite_unites * self._safe_price(self.produit.prix_unite)
            + self.quantite_sous_unites * self._safe_price(self.produit.prix_sous_unite)
            + self.quantite_sous_sous_unites * self._safe_price(self.produit.prix_sous_sous_unite)
        )

    @property
    def prix_ttc_total(self):
        return (
            self.quantite_unites * self._safe_price(self.produit.prix_unite_ttc)
            + self.quantite_sous_unites * self._safe_price(self.produit.prix_sous_unite_ttc)
            + self.quantite_sous_sous_unites * self._safe_price(self.produit.prix_sous_sous_unite_ttc)
        )

    @property
    def benefice_total(self):
        return self.prix_ttc_total - self.prix_ht_total

    @property
    def quantite_totale(self):
        return self.quantite_unites + self.quantite_sous_unites + self.quantite_sous_sous_unites

    def __repr__(self):
        return f'<Stock produit_id={self.produit_id}>'
