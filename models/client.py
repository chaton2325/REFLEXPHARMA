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
    # Facultatifs, utilises pour completer les factures (voir export_vente_pdf) :
    # une fois renseignes ici, ils sont pre-remplis (et modifiables au cas par
    # cas) sur chaque facture de ce client au lieu d'etre redemandes a chaque fois.
    adresse = db.Column(db.String(255), nullable=True)
    niu = db.Column(db.String(50), nullable=True)
    numero_cni = db.Column(db.String(50), nullable=True)
    solde = db.Column(db.Float, nullable=False, default=0.0)
    points_fidelite = db.Column(db.Integer, nullable=False, default=0)
    groupe_id = db.Column(db.Integer, db.ForeignKey('groupes_clients.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    @property
    def nom_complet(self):
        return f'{self.prenom} {self.nom}'.strip()

    def __repr__(self):
        return f'<Client {self.matricule} {self.nom_complet}>'
