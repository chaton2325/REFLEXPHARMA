from datetime import datetime

from extensions import db


class StockModification(db.Model):
    __tablename__ = 'stock_modification_logs'

    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock_entries.id'), nullable=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produits.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    numero_bl = db.Column(db.String(120), nullable=False)
    date_peremption = db.Column(db.Date, nullable=False)
    code_suivi = db.Column(db.String(255), nullable=False)
    old_qr_tire = db.Column(db.Boolean, nullable=False, default=False)
    new_qr_tire = db.Column(db.Boolean, nullable=False, default=False)

    old_quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    old_quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    old_quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_sous_unites = db.Column(db.Integer, nullable=False, default=0)
    new_quantite_sous_sous_unites = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stock = db.relationship('Stock', backref=db.backref('modifications', lazy=True))
    produit = db.relationship('Produit', backref=db.backref('stock_modifications', lazy=True))
    user = db.relationship('User', backref=db.backref('stock_modifications', lazy=True))

    @property
    def old_total(self):
        return self.old_quantite_unites + self.old_quantite_sous_unites + self.old_quantite_sous_sous_unites

    @property
    def new_total(self):
        return self.new_quantite_unites + self.new_quantite_sous_unites + self.new_quantite_sous_sous_unites

    def __repr__(self):
        return f'<StockModification {self.action} {self.code_suivi}>'
