from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for


def wants_json_response():
    return request.is_json or request.accept_mimetypes.best == "application/json"


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            if wants_json_response():
                return jsonify({"error": "Authentification requise."}), 401
            flash("Authentification requise.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view
