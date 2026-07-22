from extensions import db
from datetime import datetime


class CarteFideliteCommande(db.Model):
    """Une ligne = la carte de fidelite d'UN client, demandee dans un lot (un envoi
    e-mail groupe a l'imprimeur). Le lot regroupe toutes les cartes demandees en un
    seul e-mail, mais chaque carte garde son propre statut de reception : au cas ou
    elles n'arriveraient pas toutes ensemble, on peut les marquer recues une par une."""
    __tablename__ = 'cartes_fidelite_commandes'

    id = db.Column(db.Integer, primary_key=True)
    lot_numero = db.Column(db.String(40), nullable=False, index=True)

    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    # Snapshot : le nom/matricule restent lisibles meme si le client est supprime
    # par la suite (meme convention que ClientModificationLog, Vente, Commande...).
    client_nom = db.Column(db.String(120), nullable=False)
    client_prenom = db.Column(db.String(120), nullable=False)
    client_matricule = db.Column(db.String(50), nullable=False)

    statut = db.Column(db.String(20), nullable=False, default='en_cours', index=True)  # en_cours | recue

    demandee_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    demandee_par_nom = db.Column(db.String(120), nullable=False)
    demandee_par_prenom = db.Column(db.String(120), nullable=False)

    recue_at = db.Column(db.DateTime, nullable=True)
    recue_par_nom = db.Column(db.String(120), nullable=True)
    recue_par_prenom = db.Column(db.String(120), nullable=True)

    client = db.relationship('Client')

    @property
    def client_label(self):
        return f'{self.client_prenom} {self.client_nom}'.strip()

    def __repr__(self):
        return f'<CarteFideliteCommande {self.lot_numero} {self.client_matricule} {self.statut}>'
