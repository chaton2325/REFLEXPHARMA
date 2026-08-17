from datetime import datetime
from extensions import db

class TypeConge(db.Model):
    __tablename__ = 'types_conge'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f'<TypeConge {self.nom}>'
