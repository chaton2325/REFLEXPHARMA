from datetime import datetime
from extensions import db


class DeclarationCaisse(db.Model):
    """Comptage physique de la caisse en fin de journée, déclaré manuellement
    par un employé (une seule déclaration par date_jour). Comparé aux ventes
    en espèces réellement enregistrées ce jour-là par le module de contrôle
    (voir blueprints/admin/caisse_reports.py) -- jamais figé/recalculé ici,
    c'est un simple chiffre saisi à la main."""
    __tablename__ = 'declarations_caisse'

    id = db.Column(db.Integer, primary_key=True)
    date_jour = db.Column(db.Date, nullable=False, unique=True, index=True)
    montant_declare = db.Column(db.Float, nullable=False, default=0.0)
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref=db.backref('declarations_caisse_creees', lazy=True))

    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.relationship('User', foreign_keys=[updated_by_id], backref=db.backref('declarations_caisse_modifiees', lazy=True))

    def __repr__(self):
        return f'<DeclarationCaisse {self.date_jour} montant={self.montant_declare}>'
