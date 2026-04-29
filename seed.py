import os
from app import create_app
from extensions import db
from models.user import User
from models.stock_reason import StockReason

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

def seed():
    with app.app_context():
        # V?rifier si un superadmin existe d?j?
        if not User.query.filter_by(role='superadmin').first():
            superadmin = User(
                nom="Admin",
                prenom="Super",
                email="admin@reflexpharma.com",
                telephone="0102030405",
                adresse="Si?ge ReflexPharma",
                role="superadmin",
                poste="Directeur",
                is_active=True
            )
            superadmin.set_password("admin123")
            db.session.add(superadmin)
            print("Superadmin cr?? avec succ?s !")
        
        # Ajouter des raisons de stock par d?faut si vide
        if not StockReason.query.first():
            reasons = [
                StockReason(nom="Réapprovisionnement", type="ajout", description="Entrée normale de marchandises"),
                StockReason(nom="Correction Inventaire (+)", type="ajout", description="Ajustement positif après inventaire"),
                StockReason(nom="Retour Client", type="ajout", description="Produit retourné par un client"),
                StockReason(nom="Casse / Périmé", type="sortie", description="Produit endommagé ou date dépassée"),
                StockReason(nom="Correction Inventaire (-)", type="sortie", description="Ajustement négatif après inventaire"),
                StockReason(nom="Transfert Interne", type="sortie", description="Déplacement vers un autre rayon ou site"),
                StockReason(nom="Vente Hors Système", type="sortie", description="Sortie exceptionnelle pour vente non scannée")
            ]
            db.session.add_all(reasons)
            print("Raisons de stock par défaut créées !")

        db.session.commit()

if __name__ == '__main__':
    seed()
