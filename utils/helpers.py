"""Small, dependency-light helpers shared across the project."""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timezone
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, flash, jsonify, redirect, request, url_for
from flask_login import current_user

from utils.constants import ROLE_LABELS

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-().]{6,19}$")


def utcnow() -> datetime:
    """Naive UTC timestamp (portable across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return date.today()


def generate_reference(prefix: str = "BC") -> str:
    return f"{prefix}-{datetime.now():%y%m%d}-{secrets.token_hex(2).upper()}"


def normalise_phone(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^\d+]", "", value.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def is_valid_phone(value: str | None) -> bool:
    if not value:
        return False
    raw = value.strip()
    if not PHONE_RE.match(raw):
        return False
    digits = re.sub(r"\D", "", raw)
    return 7 <= len(digits) <= 15


def is_valid_city(value: str | None) -> bool:
    return bool(value and 2 <= len(value.strip()) <= 80)


def safe_next_url(target: str | None) -> str | None:
    """Only allow same-host relative redirects (prevents open redirects)."""
    if not target:
        return None
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    if test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc:
        return test_url.path + (f"?{test_url.query}" if test_url.query else "")
    return None


def icon_for_role(role: str) -> str:
    return {"donor": "droplet", "receiver": "hand-holding-medical", "admin": "user-shield"}.get(
        role, "user"
    )


def dashboard_url_for(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return url_for("auth.login")
    if user.role == "admin":
        return url_for("admin.dashboard")
    if user.role == "receiver":
        return url_for("receiver.dashboard")
    return url_for("donor.dashboard")


def wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    accept = request.accept_mimetypes
    return accept["application/json"] > accept["text/html"]


def role_required(*roles: str):
    """Protect a view with authentication + one of the allowed roles.

    HTML requests get a friendly redirect (or 403 when already on a
    dashboard), API requests get a JSON envelope.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                if wants_json():
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": {
                                    "code": "authentication_required",
                                    "message": "You must sign in to perform this action.",
                                },
                            }
                        ),
                        401,
                    )
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

            if current_user.role not in roles:
                if wants_json():
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": {
                                    "code": "forbidden",
                                    "message": "Your account does not have access to this resource.",
                                },
                            }
                        ),
                        403,
                    )
                abort(403)

            if not current_user.is_active:
                if wants_json():
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": {
                                    "code": "account_disabled",
                                    "message": "This account has been disabled.",
                                },
                            }
                        ),
                        403,
                    )
                abort(403)

            return view(*args, **kwargs)

        return wrapped

    return decorator


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.title())
