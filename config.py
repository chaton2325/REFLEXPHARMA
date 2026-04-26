import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-me')
    # Utilisation de DATABASE_LOCAL_URL par défaut comme vu dans testDatabase.py.py
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_LOCAL_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
