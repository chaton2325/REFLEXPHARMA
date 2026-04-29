from datetime import datetime
from extensions import db

class StockReason(db.Model):
    __tablename__ = 'stock_reasons'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'ajout' or 'sortie'
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<StockReason {self.nom} ({self.type})>'
