from extensions import db

class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    feature = db.Column(db.String(50), nullable=False) # ex: 'gestion_employes'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    poste_id = db.Column(db.Integer, db.ForeignKey('postes.id'), nullable=True)
    is_allowed = db.Column(db.Boolean, default=True)

    def __repr__(self):
        target = f"User:{self.user_id}" if self.user_id else f"Poste:{self.poste_id}"
        status = "Allow" if self.is_allowed else "Deny"
        return f'<Permission {self.feature} {target} {status}>'
