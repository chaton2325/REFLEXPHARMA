import os
from app import create_app
from extensions import db
from models.user import User

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

def seed():
    with app.app_context():
        # Vérifier si un superadmin existe déjà
        if User.query.filter_by(role='superadmin').first():
            print("Un superadmin existe déjà.")
            return

        superadmin = User(
            nom="Admin",
            prenom="Super",
            email="admin@reflexpharma.com",
            telephone="0102030405",
            adresse="Siège ReflexPharma",
            role="superadmin",
            poste="Directeur",
            is_active=True
        )
        superadmin.set_password("admin123")
        
        db.session.add(superadmin)
        db.session.commit()
        print("Superadmin créé avec succès !")
        print("Email : admin@reflexpharma.com")
        print("Mot de passe : admin123")

if __name__ == '__main__':
    seed()
