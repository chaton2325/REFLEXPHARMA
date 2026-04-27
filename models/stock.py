import re
from datetime import datetime

from extensions import db


class Stock(db.Model):
    __tablename__ = 'stock_entries'
    __table_args__ = (
        db.UniqueConstraint('produit_id', 'numero_bl', 'date_peremption', name='uq_stock_entry_batch'),
    )

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produits.id'), nullable=False)
    numero_bl = db.Column(db.String(120), nullable=False)
    date_peremption = db.Column(db.Date, nullable=False)
    code_suivi = db.Column(db.String(255), nullable=False, unique=True, index=True)
    quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    produit = db.relationship(
        'Produit',
        backref=db.backref('stocks', lazy=True, cascade='all, delete-orphan')
    )

    @staticmethod
    def _safe_price(value):
        return float(value or 0)

    @staticmethod
    def normalize_bl(numero_bl):
        normalized = re.sub(r'\s+', '', (numero_bl or '').strip().upper())
        normalized = normalized.replace('/', '-').replace('\\', '-')
        return normalized

    @classmethod
    def build_tracking_code(cls, produit_code, numero_bl, date_peremption):
        normalized_bl = cls.normalize_bl(numero_bl)
        full_date = date_peremption.strftime('%Y-%m-%d')
        return f'{produit_code}-{normalized_bl}-{full_date}'

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
        return f'<StockEntry {self.code_suivi}>'
