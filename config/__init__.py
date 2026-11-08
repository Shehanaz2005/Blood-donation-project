"""Application configuration objects."""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalise_database_url(url: str) -> str:
    """Allow the short ``postgres://`` / ``postgresql://`` form.

    SQLAlchemy 2 prefers an explicit driver.  We ship psycopg 3, so map the
    common URLs to ``postgresql+psycopg://``.  Explicit driver URLs are left
    untouched.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Config:
    """Base configuration shared by development and production."""

    BASE_DIR = BASE_DIR

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key-change-me")
    SQLALCHEMY_DATABASE_URI = _normalise_database_url(
        os.getenv("DATABASE_URL", "").strip()
    ) or f"sqlite:///{BASE_DIR / 'instance' / 'blood_connect.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Pagination
    DONORS_PER_PAGE = 9
    REQUESTS_PER_PAGE = 10
    USERS_PER_PAGE = 15

    # Domain rules
    DONATION_COOLDOWN_DAYS = int(os.getenv("DONATION_COOLDOWN_DAYS", "90"))
    MIN_DONOR_AGE = 18
    MAX_DONOR_AGE = 65
    MIN_DONOR_WEIGHT_KG = 50

    # Sessions & cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SESSION_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _as_bool(os.getenv("REMEMBER_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Forms / CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB request cap

    # Rate limiting
    RATELIMIT_ENABLED = _as_bool(os.getenv("RATELIMIT_ENABLED"), True)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Presentation
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "UTC")
    APP_NAME = "Blood Connect"
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@example.com")

    # Login hardening
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15


class DevelopmentConfig(Config):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True


class ProductionConfig(Config):
    DEBUG = False
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SERVER_NAME = "localhost.localdomain"
    SECRET_KEY = "test-secret-key"


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    name = (name or os.getenv("FLASK_ENV") or "development").lower()
    return CONFIG_MAP.get(name, DevelopmentConfig)
