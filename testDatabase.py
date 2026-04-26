import os
import dotenv
from sqlalchemy import create_engine, text

# Charger les variables d'environnement
dotenv.load_dotenv()

DATABASE_LOCAL_URL = os.getenv("DATABASE_LOCAL_URL")
DATABASE_ONLINE_URL = os.getenv("DATABASE_ONLINE_URL")

def test_local_connection():
    try:
        # Création du moteur
        engine = create_engine(DATABASE_LOCAL_URL)

        # Test de connexion
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ Connexion réussie !")
            print("Résultat test :", result.fetchone())

    except Exception as e:
        print("❌ Erreur de connexion à la base de données :")
        print(e)

def test_online_connection():
    try:
        # Création du moteur
        engine = create_engine(DATABASE_ONLINE_URL)

        # Test de connexion
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ Connexion réussie !")
            print("Résultat test :", result.fetchone())

    except Exception as e:
        print("❌ Erreur de connexion à la base de données :")
        print(e)

if __name__ == "__main__":
    print("Test de connexion à la base de données locale :")
    test_local_connection()
    
    """print("\nTest de connexion à la base de données en ligne :")
    test_online_connection()"""