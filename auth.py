"""Authentication blueprint — sessions backed by the Users tab in Google Sheets."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import UserMixin, login_required, login_user, logout_user

import sheets


class User(UserMixin):
    def __init__(self, email: str, role: str, name: str):
        self.id = email
        self.email = email
        self.role = role
        self.name = name or email.split("@", 1)[0]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def load_user(email: str) -> User | None:
    sheets.ensure_bootstrap()
    record = sheets.find_user(email)
    if not record:
        return None
    return User(
        email=record["Email"],
        role=record.get("Role", "client"),
        name=record.get("Name", ""),
    )


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        sheets.ensure_bootstrap()
        record = sheets.verify_password(email, password)
        if not record:
            flash("Invalid email or password.", "error")
            return render_template("login.html"), 401
        user = User(
            email=record["Email"],
            role=record.get("Role", "client"),
            name=record.get("Name", ""),
        )
        login_user(user)
        return redirect(url_for("main.dashboard"))
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
