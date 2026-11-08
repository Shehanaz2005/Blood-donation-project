"""Authentication and registration forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from forms.validators import (
    validate_donor_age,
    validate_not_future,
    validate_password_strength,
    validate_phone,
    validate_unique_email,
)
from utils.constants import BLOOD_GROUP_LABELS, BLOOD_GROUPS, GENDERS, PATIENT_RELATIONS


class LoginForm(FlaskForm):
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(message="Enter a valid email address."), Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in", default=False)
    submit = SubmitField("Sign in")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email.data = (self.email.data or "").strip().lower()


class DonorRegistrationForm(FlaskForm):
    full_name = StringField(
        "Full name", validators=[DataRequired(), Length(min=3, max=120)]
    )
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255), validate_unique_email],
    )
    phone = StringField(
        "Phone number",
        validators=[DataRequired(), Length(max=24), validate_phone],
        description="Receivers only see this after you accept their request (you can turn this off).",
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), validate_password_strength],
        description="Minimum 8 characters with uppercase, lowercase and a number.",
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    blood_group = SelectField(
        "Blood group",
        choices=[(group, f"{group} — {BLOOD_GROUP_LABELS[group]}") for group in BLOOD_GROUPS],
        validators=[DataRequired()],
    )
    date_of_birth = DateField(
        "Date of birth", validators=[DataRequired(), validate_donor_age]
    )
    gender = SelectField(
        "Gender",
        choices=[(gender, gender) for gender in GENDERS],
        validators=[DataRequired()],
    )
    weight_kg = DecimalField(
        "Weight (kg)",
        places=1,
        validators=[DataRequired(), NumberRange(min=50, max=300, message="Donors must weigh at least 50 kg.")],
    )
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=80)])
    address = StringField(
        "Area / address", validators=[DataRequired(), Length(min=5, max=255)]
    )
    last_donation_date = DateField(
        "Last donation date (optional)", validators=[Optional(), validate_not_future]
    )
    share_contact = BooleanField(
        "Share my phone number with a receiver after I accept their request", default=True
    )
    terms = BooleanField(
        "I confirm I meet the health requirements and agree to the terms of service",
        validators=[DataRequired(message="You must confirm the health requirements.")],
    )
    submit = SubmitField("Create donor account")


class ReceiverRegistrationForm(FlaskForm):
    full_name = StringField(
        "Full name", validators=[DataRequired(), Length(min=3, max=120)]
    )
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255), validate_unique_email],
    )
    phone = StringField(
        "Phone number", validators=[DataRequired(), Length(max=24), validate_phone]
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), validate_password_strength],
        description="Minimum 8 characters with uppercase, lowercase and a number.",
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=80)])
    address = StringField(
        "Area / address", validators=[DataRequired(), Length(min=5, max=255)]
    )
    patient_relation = SelectField(
        "This request is for",
        choices=[(relation, relation) for relation in PATIENT_RELATIONS],
        validators=[DataRequired()],
        default="Self",
    )
    terms = BooleanField(
        "I agree to use donor contact details only for legitimate blood donation requests",
        validators=[DataRequired(message="You must accept the responsible-use policy.")],
    )
    submit = SubmitField("Create receiver account")

    def validate_email(self, field):
        # Additional hedge: never allow an admin email to be re-registered.
        from models import User

        if User.query.filter(User.email == (field.data or "").strip().lower(), User.role == "admin").first():
            raise ValidationError("This email address is reserved.")
