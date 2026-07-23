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
    qr_tire = db.Column(db.Boolean, nullable=False, default=False)
    quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    # Lot cree via l'entree en stock rapide depuis une commande fournisseur (module
    # Commandes) : reference "souple" (SET NULL si la ligne est supprimee), utilisee
    # uniquement pour afficher la progression de mise en stock sur la commande.
    commande_ligne_id = db.Column(db.Integer, db.ForeignKey('commande_lignes.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    produit = db.relationship(
        'Produit',
        backref=db.backref('stocks', lazy=True, cascade='all, delete-orphan')
    )
    commande_ligne = db.relationship('CommandeLigne', backref=db.backref('stocks_lies', lazy=True))

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
    def prix_achat_total(self):
        """Cout d'achat total du lot (PA x quantites), base du benefice."""
        return (
            self.quantite_unites * self._safe_price(self.produit.prix_unite)
            + self.quantite_sous_unites * self._safe_price(self.produit.prix_sous_unite)
            + self.quantite_sous_sous_unites * self._safe_price(self.produit.prix_sous_sous_unite)
        )

    @property
    def prix_ht_total(self):
        """Valeur de vente HT totale du lot (PVHT x quantites)."""
        return (
            self.quantite_unites * self._safe_price(self.produit.prix_vente_unite_ht)
            + self.quantite_sous_unites * self._safe_price(self.produit.prix_vente_sous_unite_ht)
            + self.quantite_sous_sous_unites * self._safe_price(self.produit.prix_vente_sous_sous_unite_ht)
        )

    @property
    def prix_ttc_total(self):
        return (
            self.quantite_unites * self._safe_price(self.produit.prix_unite_ttc)
            + self.quantite_sous_unites * self._safe_price(self.produit.prix_sous_unite_ttc)
            + self.quantite_sous_sous_unites * self._safe_price(self.produit.prix_sous_sous_unite_ttc)
        )

    @property
    def taxe_total(self):
        return self.prix_ttc_total - self.prix_ht_total

    @property
    def benefice_total(self):
        """Marge (bénéfice) : valeur de vente HT - cout d'achat, hors TVA."""
        return self.prix_ht_total - self.prix_achat_total

    @property
    def tva_total(self):
        """Montant de TVA effective, distinct de la marge/bénéfice."""
        tva = self._safe_price(self.produit.effectif_tva)
        return self.prix_ht_total * (tva / 100)

    @property
    def quantite_totale(self):
        return self.quantite_unites + self.quantite_sous_unites + self.quantite_sous_sous_unites

    def __repr__(self):
        return f'<StockEntry {self.code_suivi}>'
