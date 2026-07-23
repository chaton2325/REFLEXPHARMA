from datetime import datetime, date

from extensions import db


class CodePromo(db.Model):
    __tablename__ = 'codes_promo'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True, index=True)
    pourcentage_reduction = db.Column(db.Float, nullable=False, default=0.0)
    # Enveloppe budgetaire cumulable : le code reste utilisable sur plusieurs
    # ventes jusqu'a epuisement de ce budget (pas un usage unique).
    montant_total = db.Column(db.Float, nullable=False, default=0.0)
    montant_utilise = db.Column(db.Float, nullable=False, default=0.0)
    date_debut = db.Column(db.Date, nullable=True)
    date_fin = db.Column(db.Date, nullable=True)
    actif = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    @property
    def montant_restant(self):
        return max(self.montant_total - (self.montant_utilise or 0), 0.0)

    @property
    def est_epuise(self):
        return self.montant_restant <= 0.0001

    def est_valide(self, reference_date=None):
        reference_date = reference_date or date.today()
        if not self.actif:
            return False
        if self.date_debut and reference_date < self.date_debut:
            return False
        if self.date_fin and reference_date > self.date_fin:
            return False
        if self.est_epuise:
            return False
        return True

    def __repr__(self):
        return f'<CodePromo {self.code}>'
