from datetime import datetime

from extensions import db


class GroupeClient(db.Model):
    __tablename__ = 'groupes_clients'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False, unique=True, index=True)
    description = db.Column(db.Text)
    solde = db.Column(db.Float, nullable=False, default=0.0)
    pourcentage_absorption = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    clients = db.relationship('Client', backref='groupe', lazy=True)

    def __repr__(self):
        return f'<GroupeClient {self.nom}>'
