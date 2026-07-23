from datetime import datetime

from extensions import db


class ClientModificationLog(db.Model):
    __tablename__ = 'client_modification_logs'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(30), nullable=False, index=True)
    action = db.Column(db.String(30), nullable=False, index=True)

    reference = db.Column(db.String(120), nullable=True, index=True)
    label = db.Column(db.String(255), nullable=False)

    old_values = db.Column(db.Text, nullable=True)
    new_values = db.Column(db.Text, nullable=True)
    reason = db.Column(db.Text, nullable=True)

    user_nom = db.Column(db.String(100), nullable=False)
    user_prenom = db.Column(db.String(100), nullable=False)
    user_email = db.Column(db.String(150), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)

    def __repr__(self):
        return f'<ClientModificationLog {self.entity_type} {self.action} {self.reference}>'
