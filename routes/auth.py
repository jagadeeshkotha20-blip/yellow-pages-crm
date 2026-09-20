from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        # Generic message on purpose — never reveal whether the email exists.
        generic_error = "Invalid email or password."

        if user is None:
            flash(generic_error, "danger")
            return render_template("login.html")

        if user.is_locked_out():
            minutes_left = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1)
            flash(f"Too many failed attempts. Try again in about {minutes_left} minute(s).", "danger")
            return render_template("login.html")

        if not user.check_password(password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            max_attempts = current_app.config["MAX_FAILED_LOGIN_ATTEMPTS"]
            if user.failed_login_attempts >= max_attempts:
                user.locked_until = datetime.utcnow() + timedelta(
                    minutes=current_app.config["ACCOUNT_LOCKOUT_MINUTES"]
                )
                db.session.commit()
                flash(
                    f"Too many failed attempts. Account locked for "
                    f"{current_app.config['ACCOUNT_LOCKOUT_MINUTES']} minutes.", "danger",
                )
                return render_template("login.html")
            db.session.commit()
            flash(generic_error, "danger")
            return render_template("login.html")

        if not user.is_active_employee:
            flash("This account has been deactivated. Contact your Super Admin.", "danger")
            return render_template("login.html")

        # Successful login — reset lockout counters.
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

        login_user(user)
        flash(f"Welcome back, {user.name}!", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.index"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
