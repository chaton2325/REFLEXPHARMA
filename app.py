import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for

from blueprints import auth_bp, dashboard_bp
from db import database_is_configured, ensure_superadmin, init_db


load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    @app.get("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Base de donnees initialisee depuis schema.sql.")

    @app.cli.command("seed-superadmin")
    def seed_superadmin_command():
        created, credentials = ensure_superadmin()
        if created:
            print("Superadmin cree.")
        else:
            print("Superadmin deja present.")
        print(f"Email: {credentials['email']}")
        print(f"Password: {credentials['password']}")

    if database_is_configured() and os.getenv("AUTO_INIT_DB", "false").lower() == "true":
        init_db()

    if database_is_configured() and os.getenv("AUTO_CREATE_SUPERADMIN", "true").lower() == "true":
        ensure_superadmin()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "true").lower() == "true")
