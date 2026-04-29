from datetime import datetime

from extensions import db


class StockExitLog(db.Model):
    __tablename__ = 'stock_exit_logs'

    id = db.Column(db.Integer, primary_key=True)

    stock_id = db.Column(db.Integer, nullable=False, index=True)
    produit_id = db.Column(db.Integer, nullable=False, index=True)
    produit_nom = db.Column(db.String(200), nullable=False)
    produit_code = db.Column(db.String(50), nullable=False)
    numero_bl = db.Column(db.String(120), nullable=False)
    date_peremption = db.Column(db.Date, nullable=False)
    code_suivi = db.Column(db.String(255), nullable=False, index=True)

    user_id = db.Column(db.Integer, nullable=False, index=True)
    user_nom = db.Column(db.String(100), nullable=False)
    user_prenom = db.Column(db.String(100), nullable=False)
    user_email = db.Column(db.String(150), nullable=False)

    reason_id = db.Column(db.Integer, nullable=False, index=True)
    reason_nom = db.Column(db.String(120), nullable=False)

    quantite_unites_sortie = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_unites_sortie = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_sous_unites_sortie = db.Column(db.Integer, nullable=False, default=0)

    old_quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    old_quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    old_quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<StockExitLog {self.produit_code} {self.code_suivi}>'
