"""Blood Connect — application factory.

Run locally with:
    python run.py
or:
    flask --app run.py run --debug
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from config import get_config
from extensions import csrf, db, limiter, login_manager, migrate

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


# ----------------------------------------------------------------------
# Template helpers
# ----------------------------------------------------------------------
def _localize(value: datetime | None) -> datetime | None:
    if not value:
        return None
    from flask import current_app

    tz_name = current_app.config.get("APP_TIMEZONE", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
    return value.replace(tzinfo=timezone.utc).astimezone(tz)


def register_template_helpers(app: Flask) -> None:
    @app.template_filter("dt")
    def format_datetime(value, fmt: str = "%d %b %Y, %I:%M %p"):
        local = _localize(value)
        return local.strftime(fmt) if local else "—"

    @app.template_filter("d")
    def format_date(value, fmt: str = "%d %b %Y"):
        if not value:
            return "—"
        return value.strftime(fmt)

    @app.template_filter("timeago")
    def timeago(value):
        if not value:
            return "—"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = now - value
        seconds = max(int(delta.total_seconds()), 0)
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} min ago"
        if seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hr ago"
        if seconds < 604800:
            days = seconds // 86400
            return f"{days} day{'s' if days > 1 else ''} ago"
        return _localize(value).strftime("%d %b %Y")

    @app.template_filter("initials")
    def initials(value):
        parts = [part for part in str(value or "").split() if part]
        if not parts:
            return "BC"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @app.template_filter("mask_phone")
    def mask_phone(value):
        if not value:
            return "—"
        digits = re.sub(r"\D", "", value)
        if len(digits) <= 5:
            return "•" * len(digits)
        return f"{digits[:3]} {'•' * max(len(digits) - 6, 3)} {digits[-3:]}"

    @app.template_filter("nl2br")
    def nl2br(value):
        from markupsafe import Markup, escape

        if not value:
            return ""
        return Markup("<br>".join(escape(value).split("\n")))


# ----------------------------------------------------------------------
# Application factory
# ----------------------------------------------------------------------
def create_app(config_name: str | None = None, test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    Path(app.root_path, "instance").mkdir(exist_ok=True)

    # Logging
    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Models must be imported so migrations can see them.
    with app.app_context():
        import models  # noqa: F401

    register_template_helpers(app)
    register_blueprints(app)
    register_context_processors(app)
    register_error_handlers(app)
    register_request_hooks(app)
    register_cli(app)

    return app


def register_blueprints(app: Flask) -> None:
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.auth import auth_bp
    from routes.donor import donor_bp
    from routes.main import main_bp
    from routes.receiver import receiver_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(donor_bp, url_prefix="/donor")
    app.register_blueprint(receiver_bp, url_prefix="/receiver")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api/v1")


def register_context_processors(app: Flask) -> None:
    from utils.constants import (
        ACTIVE_REQUEST_STATUSES,
        BLOOD_GROUP_LABELS,
        BLOOD_GROUP_RARITY,
        BLOOD_GROUPS,
        GENDERS,
        NAV_LINKS,
        PATIENT_RELATIONS,
        REPORT_STATUS_META,
        ROLES,
        STATUS_META,
        URGENCY_META,
    )

    @app.context_processor
    def inject_globals():
        unread = 0
        recent_notifications = []
        if current_user.is_authenticated:
            unread = current_user.unread_notifications
            recent_notifications = current_user.notifications.limit(5).all()
        return {
            "app_name": app.config.get("APP_NAME", "Blood Connect"),
            "current_year": datetime.now().year,
            "nav_links": NAV_LINKS,
            "blood_groups": BLOOD_GROUPS,
            "blood_group_labels": BLOOD_GROUP_LABELS,
            "blood_group_rarity": BLOOD_GROUP_RARITY,
            "status_meta": STATUS_META,
            "urgency_meta": URGENCY_META,
            "report_status_meta": REPORT_STATUS_META,
            "active_request_statuses": ACTIVE_REQUEST_STATUSES,
            "genders": GENDERS,
            "patient_relations": PATIENT_RELATIONS,
            "roles": ROLES,
            "unread_notifications": unread,
            "recent_notifications": recent_notifications,
            "donation_cooldown_days": app.config.get("DONATION_COOLDOWN_DAYS", 90),
        }

    # Imported macros (``{% from ... import ... %}``) do not receive the
    # template context by default, so expose the static lookup tables as
    # Jinja globals as well. This keeps ``status_badge``/``urgency_badge``
    # working everywhere without adding ``with context`` to every template.
    app.jinja_env.globals.update(
        status_meta=STATUS_META,
        urgency_meta=URGENCY_META,
        report_status_meta=REPORT_STATUS_META,
        blood_group_labels=BLOOD_GROUP_LABELS,
        blood_group_rarity=BLOOD_GROUP_RARITY,
        blood_groups=BLOOD_GROUPS,
        active_request_statuses=ACTIVE_REQUEST_STATUSES,
        genders=GENDERS,
        patient_relations=PATIENT_RELATIONS,
        roles=ROLES,
    )


# ----------------------------------------------------------------------
# Authentication loader
# ----------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id: str):
    from models import User

    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if not user or not user.is_active:
        return None
    return user


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "authentication_required",
                        "message": "Authentication is required for this endpoint.",
                    },
                }
            ),
            401,
        )
    flash("Please sign in to continue.", "warning")
    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


# ----------------------------------------------------------------------
# Request hooks
# ----------------------------------------------------------------------
def register_request_hooks(app: Flask) -> None:
    @app.before_request
    def enforce_active_account():
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("Your account has been disabled. Contact support for help.", "danger")
            return redirect(url_for("auth.login"))

    @app.before_request
    def mark_session_permanent():
        from flask import session

        if current_user.is_authenticated:
            session.permanent = True

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if current_user.is_authenticated and not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store, private")
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


# ----------------------------------------------------------------------
# Error handlers
# ----------------------------------------------------------------------
def _error_payload(code: str, message: str):
    return jsonify({"ok": False, "error": {"code": code, "message": message}})


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf(error):
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return _error_payload("csrf_failed", "Your form session expired. Refresh the page and try again."), 400
        return (
            render_template(
                "errors/400.html",
                title="Session expired",
                message="Your form session expired for security reasons. Refresh the page and try again.",
            ),
            400,
        )

    @app.errorhandler(400)
    def bad_request(error):
        if request.path.startswith("/api/"):
            return _error_payload("bad_request", "The request could not be processed."), 400
        return (
            render_template(
                "errors/400.html",
                title="Bad request",
                message=getattr(error, "description", "The request could not be processed."),
            ),
            400,
        )

    @app.errorhandler(403)
    def forbidden(error):
        if request.path.startswith("/api/"):
            return _error_payload("forbidden", "You do not have access to this resource."), 403
        return (
            render_template(
                "errors/403.html",
                title="Access denied",
                message="You do not have permission to view this page.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return _error_payload("not_found", "The requested resource does not exist."), 404
        return (
            render_template(
                "errors/404.html",
                title="Page not found",
                message="The page you are looking for may have been moved or no longer exists.",
            ),
            404,
        )

    @app.errorhandler(413)
    def too_large(error):
        if request.path.startswith("/api/"):
            return _error_payload("payload_too_large", "The request body is too large."), 413
        return (
            render_template(
                "errors/400.html",
                title="Upload too large",
                message="The data you submitted is too large. Please reduce it and try again.",
            ),
            413,
        )

    @app.errorhandler(429)
    def rate_limited(error):
        if request.path.startswith("/api/"):
            return _error_payload("rate_limited", "Too many requests. Please slow down and try again shortly."), 429
        return (
            render_template(
                "errors/429.html",
                title="Slow down",
                message="Too many attempts. Please wait a minute and try again.",
            ),
            429,
        )

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        if request.path.startswith("/api/"):
            return _error_payload("server_error", "An unexpected error occurred."), 500
        return (
            render_template(
                "errors/500.html",
                title="Something went wrong",
                message="We hit an unexpected error. Please try again.",
            ),
            500,
        )

    @app.errorhandler(HTTPException)
    def http_exception(error):
        return (
            render_template(
                "errors/400.html",
                title=error.name,
                message=error.description,
            ),
            error.code,
        )


# ----------------------------------------------------------------------
# CLI commands
# ----------------------------------------------------------------------
def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create tables directly (quick start; use `flask db upgrade` for migrations)."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Admin name")
    @click.option("--email", prompt="Admin email")
    @click.option(
        "--password",
        prompt="Password",
        hide_input=True,
        confirmation_prompt=True,
    )
    @click.option("--super-admin", is_flag=True, default=False, help="Allow managing other admins.")
    def create_admin(name, email, password, super_admin):
        """Create an administrator account (safe to run repeatedly)."""
        from models import AdminProfile, User

        email = email.strip().lower()
        if not email or "@" not in email:
            raise click.ClickException("Enter a valid email address.")
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")

        user = User.query.filter_by(email=email).first()
        if user and user.role != "admin":
            raise click.ClickException(
                f"{email} belongs to a {user.role} account. Use a different email."
            )
        if not user:
            user = User(
                full_name=name.strip(),
                email=email,
                role="admin",
                phone=None,
                is_active=True,
            )
            db.session.add(user)
        user.full_name = name.strip()
        user.role = "admin"
        user.is_active = True
        user.set_password(password)
        db.session.flush()
        if not user.admin_profile:
            user.admin_profile = AdminProfile(
                title="Platform Administrator", can_manage_admins=super_admin
            )
        user.admin_profile.can_manage_admins = super_admin or user.admin_profile.can_manage_admins
        db.session.commit()
        click.echo(f"Administrator ready: {email}")

    @app.cli.command("expire-requests")
    def expire_requests():
        """Mark pending requests past their needed-by date as expired."""
        from services.requests import expire_overdue_requests

        count = expire_overdue_requests()
        click.echo(f"Expired {count} request(s).")

    @app.cli.command("seed-demo")
    @click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
    def seed_demo(yes):
        """Insert optional demo donors/receivers so you can explore the UI.

        Never required by the application; do not run it on production data.
        """
        if not yes:
            click.confirm(
                "This will add demo accounts to the current database. Continue?", abort=True
            )
        from demo_seed import seed_demo_data

        summary = seed_demo_data()
        click.echo(
            f"Demo data ready: {summary['donors']} donors, {summary['receivers']} receivers, "
            f"{summary['requests']} requests. Password for all demo accounts: {summary['password']}"
        )


app = create_app()
