from datetime import datetime

from extensions import db


class StockExitLog(db.Model):
    __tablename__ = 'stock_exit_logs'

    id = db.Column(db.Integer, primary_key=True)

    produit_nom = db.Column(db.String(200), nullable=False)
    produit_code = db.Column(db.String(50), nullable=False)
    fournisseur_nom = db.Column(db.String(100), nullable=True)
    groupe_fournisseur_nom = db.Column(db.String(100), nullable=True)
    numero_bl = db.Column(db.String(120), nullable=False)
    date_peremption = db.Column(db.Date, nullable=False)
    code_suivi = db.Column(db.String(255), nullable=False, index=True)

    mise_en_stock_at = db.Column(db.DateTime, nullable=True)
    mise_en_stock_user_nom = db.Column(db.String(100), nullable=True)
    mise_en_stock_user_prenom = db.Column(db.String(100), nullable=True)
    mise_en_stock_user_email = db.Column(db.String(150), nullable=True)

    user_nom = db.Column(db.String(100), nullable=False)
    user_prenom = db.Column(db.String(100), nullable=False)
    user_email = db.Column(db.String(150), nullable=False)

    reason_nom = db.Column(db.String(120), nullable=False)

    quantite_unites_sortie = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_unites_sortie = db.Column(db.Integer, nullable=False, default=0)
    quantite_sous_sous_unites_sortie = db.Column(db.Integer, nullable=False, default=0)

    prix_unite_ht = db.Column(db.Float, nullable=False, default=0.0)
    prix_sous_unite_ht = db.Column(db.Float, nullable=False, default=0.0)
    prix_sous_sous_unite_ht = db.Column(db.Float, nullable=False, default=0.0)
    prix_unite_ttc = db.Column(db.Float, nullable=False, default=0.0)
    prix_sous_unite_ttc = db.Column(db.Float, nullable=False, default=0.0)
    prix_sous_sous_unite_ttc = db.Column(db.Float, nullable=False, default=0.0)
    tva_pourcentage = db.Column(db.Float, nullable=False, default=0.0)
    total_sortie_ht = db.Column(db.Float, nullable=False, default=0.0)
    total_sortie_ttc = db.Column(db.Float, nullable=False, default=0.0)

    old_quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    old_quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    old_quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<StockExitLog {self.produit_code} {self.code_suivi}>'
