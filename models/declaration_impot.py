from datetime import datetime
from extensions import db


class DeclarationImpot(db.Model):
    __tablename__ = 'declarations_impots'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), nullable=False, unique=True, index=True)
    periode_debut = db.Column(db.Date, nullable=False)
    periode_fin = db.Column(db.Date, nullable=False)
    statut = db.Column(db.String(30), nullable=False, default='en_preparation')  # 'en_preparation', 'declaree'
    note = db.Column(db.Text)

    # Totaux gelés au moment où la période est marquée comme déclarée
    nb_ventes = db.Column(db.Integer, nullable=False, default=0)
    total_ht = db.Column(db.Float, nullable=False, default=0.0)
    total_tva = db.Column(db.Float, nullable=False, default=0.0)
    total_benefice = db.Column(db.Float, nullable=False, default=0.0)
    total_ttc = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref=db.backref('declarations_impots_creees', lazy=True))

    declared_at = db.Column(db.DateTime, nullable=True)
    declared_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    declared_by = db.relationship('User', foreign_keys=[declared_by_id], backref=db.backref('declarations_impots_validees', lazy=True))

    @property
    def est_declaree(self):
        return self.statut == 'declaree'

    @property
    def periode_label(self):
        if not self.periode_debut or not self.periode_fin:
            return '-'
        return f"{self.periode_debut.strftime('%d/%m/%Y')} au {self.periode_fin.strftime('%d/%m/%Y')}"

    def __repr__(self):
        return f'<DeclarationImpot {self.reference} ({self.periode_label}) {self.statut}>'
