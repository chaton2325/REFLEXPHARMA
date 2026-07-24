import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-me')
    # Utilisation de DATABASE_LOCAL_URL par défaut comme vu dans testDatabase.py.py
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_LOCAL_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

    # Module de licence : URL de l'API de ReflexPharma Admin, secret HMAC local
    # (protège license_cache.expires_at_hmac contre une modification directe en base
    # locale) et intervalle de re-vérification périodique en arrière-plan.
    LICENSE_ADMIN_API_BASE_URL = os.getenv('LICENSE_ADMIN_API_BASE_URL', 'http://localhost:5001')
    LICENSE_HMAC_SECRET_LOCAL = os.getenv('LICENSE_HMAC_SECRET_LOCAL', 'change-me-local-secret')
    LICENSE_CHECK_INTERVAL_MINUTES = int(os.getenv('LICENSE_CHECK_INTERVAL_MINUTES', '60'))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
