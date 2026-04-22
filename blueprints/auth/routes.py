from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text
from werkzeug.security import check_password_hash

from blueprints.auth.decorators import login_required, wants_json_response
from db import get_engine


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("auth.me"))
        return render_template("auth/login.html")

    payload = request.get_json(silent=True) if request.is_json else request.form
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        if wants_json_response():
            return jsonify({"error": "Email et mot de passe sont obligatoires."}), 400
        flash("Email et mot de passe sont obligatoires.", "error")
        return render_template("auth/login.html", email=email), 400

    with get_engine().begin() as connection:
        user = connection.execute(
            text(
                """
                SELECT id, full_name, email, password_hash, role, is_active
                FROM users
                WHERE email = :email
                """
            ),
            {"email": email},
        ).mappings().first()

        if not user or not check_password_hash(user["password_hash"], password):
            if wants_json_response():
                return jsonify({"error": "Identifiants invalides."}), 401
            flash("Identifiants invalides.", "error")
            return render_template("auth/login.html", email=email), 401

        if not user["is_active"]:
            if wants_json_response():
                return jsonify({"error": "Compte desactive."}), 403
            flash("Compte desactive.", "error")
            return render_template("auth/login.html", email=email), 403

        connection.execute(
            text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :user_id"),
            {"user_id": user["id"]},
        )

    session["user_id"] = user["id"]
    session["user_role"] = user["role"]

    if wants_json_response():
        return jsonify(
            {
                "message": "Connexion reussie.",
                "user": {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "role": user["role"],
                },
            }
        )

    flash("Connexion reussie.", "success")
    return redirect(url_for("dashboard.dashboard_home"))


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    if wants_json_response():
        return jsonify({"message": "Deconnexion reussie."})
    flash("Deconnexion reussie.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.get("/me")
@login_required
def me():
    with get_engine().begin() as connection:
        user = connection.execute(
            text(
                """
                SELECT id, full_name, email, role, is_active, last_login, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": session["user_id"]},
        ).mappings().first()

    if not user:
        session.clear()
        if wants_json_response():
            return jsonify({"error": "Utilisateur introuvable."}), 404
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("auth.login"))

    if wants_json_response():
        return jsonify({"user": dict(user)})

    return redirect(url_for("dashboard.dashboard_home"))
