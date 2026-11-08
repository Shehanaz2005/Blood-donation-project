"""Donor profile forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional

from forms.validators import (
    validate_donor_age,
    validate_not_future,
    validate_phone,
    validate_unique_email,
)
from utils.constants import BLOOD_GROUP_LABELS, BLOOD_GROUPS, GENDERS


class DonorProfileForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=3, max=120)])
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255), validate_unique_email],
    )
    phone = StringField("Phone number", validators=[DataRequired(), Length(max=24), validate_phone])
    blood_group = SelectField(
        "Blood group",
        choices=[(group, f"{group} — {BLOOD_GROUP_LABELS[group]}") for group in BLOOD_GROUPS],
        validators=[DataRequired()],
    )
    date_of_birth = DateField("Date of birth", validators=[DataRequired(), validate_donor_age])
    gender = SelectField(
        "Gender", choices=[(gender, gender) for gender in GENDERS], validators=[DataRequired()]
    )
    weight_kg = DecimalField(
        "Weight (kg)",
        places=1,
        validators=[DataRequired(), NumberRange(min=50, max=300, message="Donors must weigh at least 50 kg.")],
    )
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=80)])
    address = StringField("Area / address", validators=[DataRequired(), Length(min=5, max=255)])
    last_donation_date = DateField(
        "Last donation date", validators=[Optional(), validate_not_future]
    )
    share_contact = BooleanField("Share my phone number with receivers after I accept a request")
    bio = TextAreaField(
        "About me (optional)",
        validators=[Optional(), Length(max=1000)],
        description="A short note helps receivers trust your profile. Do not include medical records.",
    )
    submit = SubmitField("Save profile")


class AvailabilityForm(FlaskForm):
    available = BooleanField("Available to donate")
    submit = SubmitField("Update availability")
