from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    telephone = db.Column(db.String(20))
    adresse = db.Column(db.Text)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # superadmin, admin, employee
    poste = db.Column(db.String(100))
    date_prise_poste = db.Column(db.Date)
    salaire_mensuel = db.Column(db.Float)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_superadmin(self):
        return self.role == 'superadmin'

    def is_admin(self):
        return self.role in ['superadmin', 'admin']

    def has_permission(self, feature):
        # Le superadmin a tous les droits par défaut
        if self.role == 'superadmin':
            return True
            
        from models.permission import Permission
        from models.poste import Poste
        
        # 1. Priorité : Permission individuelle de l'utilisateur
        user_perm = Permission.query.filter_by(feature=feature, user_id=self.id).first()
        if user_perm is not None:
            return user_perm.is_allowed
            
        # 2. Secondaire : Permission associée au poste (groupe)
        if self.poste:
            poste_obj = Poste.query.filter_by(nom=self.poste).first()
            if poste_obj:
                poste_perm = Permission.query.filter_by(feature=feature, poste_id=poste_obj.id).first()
                if poste_perm is not None:
                    return poste_perm.is_allowed
        
        # Par défaut, accès refusé si rien n'est défini
        return False

    def __repr__(self):
        return f'<User {self.email}>'
