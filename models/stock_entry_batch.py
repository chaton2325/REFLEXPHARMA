from datetime import datetime
from extensions import db


class StockEntryBatch(db.Model):
    """Une soumission du panier « Nouvelle entrée en stock » (module Stock) --
    regroupe une ou plusieurs lignes (une par produit ajouté au panier), pour
    pouvoir générer un bon PDF unique et retrouver l'historique de CET envoi
    précis, distinct de l'audit générique ligne-par-ligne (voir
    StockModification.stock_entry_batch_id). La raison est snapshotée (texte
    libre si saisi, sinon nom de la raison prédéfinie au moment de l'envoi)
    pour rester lisible même si la raison prédéfinie est supprimée ensuite."""
    __tablename__ = 'stock_entry_batches'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(40), unique=True, nullable=False, index=True)

    reason_id = db.Column(db.Integer, db.ForeignKey('stock_reasons.id', ondelete='SET NULL'), nullable=True)
    stock_reason = db.relationship('StockReason')
    reason_text = db.Column(db.Text, nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_by = db.relationship('User')
    created_by_nom = db.Column(db.String(200), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    @property
    def effective_reason(self):
        """Raison affichée : texte libre si saisi, sinon le nom de la raison
        prédéfinie -- mêmes règles que StockModification.effective_reason."""
        if self.reason_text:
            return self.reason_text
        if self.stock_reason:
            return self.stock_reason.nom
        return None

    @property
    def nb_lignes(self):
        return len(self.modifications)

    @property
    def quantite_totale_ajoutee(self):
        return sum(m.delta_total for m in self.modifications)

    def __repr__(self):
        return f'<StockEntryBatch {self.numero}>'
