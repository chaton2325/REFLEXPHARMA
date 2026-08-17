from datetime import datetime, date
from extensions import db

class Conge(db.Model):
    __tablename__ = 'conges'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type_conge_id = db.Column(db.Integer, db.ForeignKey('types_conge.id'), nullable=True)
    # Nom du type snapshote au moment de la creation (meme principe que
    # Vente.raison_annulation_nom) : un conge deja enregistre garde son type
    # meme si celui-ci est renomme/supprime ensuite de la liste geree.
    type_conge_nom = db.Column(db.String(200))
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    commentaire = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    employe = db.relationship('User', foreign_keys=[user_id])
    cree_par = db.relationship('User', foreign_keys=[created_by_id])

    @property
    def nb_jours(self):
        return (self.date_fin - self.date_debut).days + 1

    @property
    def statut(self):
        today = date.today()
        if self.date_fin < today:
            return 'Terminé'
        if self.date_debut > today:
            return 'À venir'
        return 'En cours'

    def __repr__(self):
        return f'<Conge user={self.user_id} {self.date_debut}..{self.date_fin}>'
