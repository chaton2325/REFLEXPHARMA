from collections import Counter

from flask import Blueprint, redirect, render_template, session, url_for

from blueprints.auth.decorators import login_required
from db import fetch_all, fetch_one, safe_db_call


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/admin")


ROLE_LABELS = {
    "superadmin": "Superadmin",
    "admin": "Administrateur",
    "employee": "Employe",
    "cashier": "Caissier",
}


def load_admin_context():
    user = fetch_one(
        """
        SELECT id, full_name, email, role, is_active, last_login, created_at
        FROM users
        WHERE id = :user_id
        """,
        {"user_id": session["user_id"]},
    )

    metrics = {
        "users_total": fetch_one("SELECT COUNT(*) AS value FROM users")["value"],
        "employees_total": fetch_one("SELECT COUNT(*) AS value FROM employees")["value"],
        "active_users": fetch_one(
            "SELECT COUNT(*) AS value FROM users WHERE is_active = TRUE"
        )["value"],
        "admins_total": fetch_one(
            """
            SELECT COUNT(*) AS value
            FROM users
            WHERE role IN ('superadmin', 'admin')
            """
        )["value"],
    }

    role_rows = fetch_all(
        """
        SELECT role, COUNT(*) AS total
        FROM users
        GROUP BY role
        ORDER BY total DESC, role ASC
        """
    )
    role_stats = [
        {"role": row["role"], "label": ROLE_LABELS.get(row["role"], row["role"]), "total": row["total"]}
        for row in role_rows
    ]

    recent_users = fetch_all(
        """
        SELECT id, full_name, email, role, is_active, created_at, last_login
        FROM users
        ORDER BY created_at DESC
        LIMIT 6
        """
    )

    recent_employees = fetch_all(
        """
        SELECT
            e.id,
            COALESCE(u.full_name, 'Profil non lie') AS full_name,
            COALESCE(u.email, '-') AS email,
            e.contract_type,
            e.status,
            e.hire_date,
            e.base_salary
        FROM employees e
        LEFT JOIN users u ON u.id = e.user_id
        ORDER BY e.id DESC
        LIMIT 6
        """
    )

    return {
        "current_user": user,
        "metrics": metrics,
        "role_stats": role_stats,
        "recent_users": recent_users,
        "recent_employees": recent_employees,
    }


def load_users_page():
    users = fetch_all(
        """
        SELECT
            u.id,
            u.full_name,
            u.email,
            u.phone,
            u.role,
            u.language,
            u.is_active,
            u.last_login,
            u.created_at,
            CASE WHEN e.id IS NULL THEN FALSE ELSE TRUE END AS has_employee_profile,
            COUNT(ama.id) AS module_assignments
        FROM users u
        LEFT JOIN employees e ON e.user_id = u.id
        LEFT JOIN admin_module_assignments ama ON ama.admin_id = u.id
        GROUP BY u.id, e.id
        ORDER BY u.created_at DESC
        """
    )

    role_counter = Counter(user["role"] for user in users)
    overview = {
        "total": len(users),
        "active": sum(1 for user in users if user["is_active"]),
        "inactive": sum(1 for user in users if not user["is_active"]),
        "with_employee_profile": sum(1 for user in users if user["has_employee_profile"]),
        "roles": [
            {
                "role": role,
                "label": ROLE_LABELS.get(role, role),
                "total": total,
            }
            for role, total in sorted(role_counter.items(), key=lambda item: (-item[1], item[0]))
        ],
    }

    return {"users": users, "overview": overview}


def load_employees_page():
    employees = fetch_all(
        """
        SELECT
            e.id,
            e.user_id,
            COALESCE(u.full_name, 'Profil non lie') AS full_name,
            COALESCE(u.email, '-') AS email,
            COALESCE(e.phone, u.phone, '-') AS phone,
            e.national_id,
            e.hire_date,
            e.contract_type,
            e.base_salary,
            e.status,
            COUNT(p.id) AS payroll_count
        FROM employees e
        LEFT JOIN users u ON u.id = e.user_id
        LEFT JOIN payrolls p ON p.employee_id = e.id
        GROUP BY e.id, u.id
        ORDER BY e.id DESC
        """
    )

    status_counter = Counter(employee["status"] or "indefini" for employee in employees)
    overview = {
        "total": len(employees),
        "linked_users": sum(1 for employee in employees if employee["user_id"]),
        "average_salary": round(
            sum(float(employee["base_salary"] or 0) for employee in employees) / len(employees), 2
        )
        if employees
        else 0,
        "statuses": [
            {"status": status, "total": total}
            for status, total in sorted(status_counter.items(), key=lambda item: (-item[1], item[0]))
        ],
    }

    return {"employees": employees, "overview": overview}


def render_admin_page(template_name, page_title, current_section, loader):
    payload, error = safe_db_call(
        lambda: load_admin_context() | loader(),
        {
            "current_user": {
                "full_name": "Utilisateur",
                "email": "-",
                "role": session.get("user_role", "user"),
            }
        },
    )
    payload["db_error"] = error
    payload["page_title"] = page_title
    payload["current_section"] = current_section
    return render_template(template_name, **payload)


@dashboard_bp.get("/")
@login_required
def index():
    return redirect(url_for("dashboard.dashboard_home"))


@dashboard_bp.get("/dashboard")
@login_required
def dashboard_home():
    return render_admin_page(
        "admin/dashboard.html",
        "Dashboard",
        "dashboard",
        lambda: {},
    )


@dashboard_bp.get("/users")
@login_required
def users():
    return render_admin_page(
        "admin/users.html",
        "Utilisateurs et roles",
        "users",
        load_users_page,
    )


@dashboard_bp.get("/employees")
@login_required
def employees():
    return render_admin_page(
        "admin/employees.html",
        "Employes",
        "employees",
        load_employees_page,
    )
