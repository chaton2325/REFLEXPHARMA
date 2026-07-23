from datetime import datetime
from extensions import db


class RaisonFinanciere(db.Model):
    """Raison proposée lors de la création d'une opération financière. Chaque
    raison appartient à un type ('encaissement' ou 'decaissement') et n'est
    proposée que pour les opérations de ce type. L'opération enregistre le NOM
    de la raison en texte (photo) : supprimer une raison de cette liste ne
    modifie jamais les opérations déjà enregistrées."""
    __tablename__ = 'raisons_financieres'
    __table_args__ = (
        db.UniqueConstraint('type', 'nom', name='uq_raison_financiere_type_nom'),
    )

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # 'encaissement' ou 'decaissement'
    nom = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f'<RaisonFinanciere {self.type}: {self.nom}>'


class OperationFinanciere(db.Model):
    """Mouvement de caisse manuel (encaissement ou décaissement), avec une raison
    obligatoire pour la traçabilité. Ajuste uniquement le solde affiché dans le
    module Finance : n'écrit jamais dans Vente/VenteLigne, donc le chiffre
    d'affaires et le bénéfice (calculés à partir des ventes) restent des données
    pures, jamais modifiées par ces opérations.
    """
    __tablename__ = 'operations_financieres'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # 'encaissement' ou 'decaissement'
    montant = db.Column(db.Float, nullable=False, default=0.0)
    raison = db.Column(db.String(200), nullable=False)
    note = db.Column(db.Text, nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    created_by_nom = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    @property
    def impact_solde(self):
        return self.montant if self.type == 'encaissement' else -self.montant

    def __repr__(self):
        return f'<OperationFinanciere {self.type} {self.montant} ({self.raison})>'
