"""Reusable WTForms validators."""
from __future__ import annotations

import re
from datetime import date

from flask_login import current_user
from wtforms.validators import ValidationError

from models import User
from utils.helpers import is_valid_phone

WEAK_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "letmein123",
    "blood123",
    "admin123",
    "iloveyou",
}


def validate_password_strength(form, field):
    value = field.data or ""
    if len(value) < 8:
        raise ValidationError("Use at least 8 characters.")
    if not re.search(r"[A-Z]", value):
        raise ValidationError("Add at least one uppercase letter.")
    if not re.search(r"[a-z]", value):
        raise ValidationError("Add at least one lowercase letter.")
    if not re.search(r"\d", value):
        raise ValidationError("Add at least one number.")
    if value.lower() in WEAK_PASSWORDS:
        raise ValidationError("This password is too common. Choose a stronger one.")


def validate_unique_email(form, field):
    email = (field.data or "").strip().lower()
    query = User.query.filter(User.email == email)
    if current_user and current_user.is_authenticated:
        query = query.filter(User.id != current_user.id)
    if query.first():
        raise ValidationError("An account with this email already exists. Try signing in instead.")


def validate_phone(form, field):
    if not is_valid_phone(field.data):
        raise ValidationError("Enter a valid phone number (7-15 digits, optional + and spaces).")


def validate_not_future(form, field):
    if field.data and field.data > date.today():
        raise ValidationError("The date cannot be in the future.")


def validate_donor_age(form, field):
    dob = field.data
    if not dob:
        return
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18:
        raise ValidationError("Donors must be at least 18 years old.")
    if age > 65:
        raise ValidationError("Donors must be 65 years old or younger.")
    if dob.year < 1900:
        raise ValidationError("Enter a valid date of birth.")


def validate_needed_by(form, field):
    if field.data and field.data < date.today():
        raise ValidationError("Choose today or a future date.")
