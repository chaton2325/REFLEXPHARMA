from datetime import datetime

from extensions import db


class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(50), nullable=False, unique=True, index=True)
    nom = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), nullable=True, unique=True, index=True)
    telephone = db.Column(db.String(30), nullable=True)
    solde = db.Column(db.Float, nullable=False, default=0.0)
    groupe_id = db.Column(db.Integer, db.ForeignKey('groupes_clients.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def nom_complet(self):
        return f'{self.prenom} {self.nom}'.strip()

    def __repr__(self):
        return f'<Client {self.matricule} {self.nom_complet}>'
