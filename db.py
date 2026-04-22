import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_database_url():
    database_url = os.getenv("DATABASE_LOCAL_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_LOCAL_URL ou DATABASE_URL doit etre defini dans les variables d'environnement."
        )
    return database_url


def database_is_configured():
    return bool(os.getenv("DATABASE_LOCAL_URL") or os.getenv("DATABASE_URL"))


def get_engine():
    return create_engine(get_database_url(), future=True)


def init_db():
    with get_engine().begin() as connection:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        statements = [statement.strip() for statement in schema_sql.split(";") if statement.strip()]
        for statement in statements:
            connection.execute(text(statement))


def ensure_superadmin():
    email = os.getenv("SUPERADMIN_EMAIL", "superadmin@reflexpharma.local")
    password = os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!")
    full_name = os.getenv("SUPERADMIN_NAME", "Super Administrateur")

    with get_engine().begin() as connection:
        existing_user = connection.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()

        if existing_user:
            return False, {"email": email, "password": password}

        connection.execute(
            text(
                """
                INSERT INTO users (full_name, email, password_hash, role, is_active)
                VALUES (:full_name, :email, :password_hash, 'superadmin', TRUE)
                """
            ),
            {
                "full_name": full_name,
                "email": email,
                "password_hash": generate_password_hash(password),
            },
        )

    return True, {"email": email, "password": password}


def fetch_all(query, params=None):
    with get_engine().connect() as connection:
        return connection.execute(text(query), params or {}).mappings().all()


def fetch_one(query, params=None):
    with get_engine().connect() as connection:
        return connection.execute(text(query), params or {}).mappings().first()


def fetch_value(query, params=None, default=None):
    with get_engine().connect() as connection:
        value = connection.execute(text(query), params or {}).scalar()
    return default if value is None else value


def safe_db_call(callback, fallback):
    try:
        return callback(), None
    except (RuntimeError, SQLAlchemyError) as exc:
        return fallback, str(exc)
