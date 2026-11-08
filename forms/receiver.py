"""Receiver profile, blood request and report forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, Optional

from forms.validators import validate_needed_by, validate_phone, validate_unique_email
from utils.constants import PATIENT_RELATIONS, REPORT_REASONS, URGENCY_LEVELS, URGENCY_META


class ReceiverProfileForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=3, max=120)])
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255), validate_unique_email],
    )
    phone = StringField("Phone number", validators=[DataRequired(), Length(max=24), validate_phone])
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=80)])
    address = StringField("Area / address", validators=[DataRequired(), Length(min=5, max=255)])
    preferred_hospital = StringField("Preferred hospital", validators=[Optional(), Length(max=150)])
    patient_relation = SelectField(
        "This request is for",
        choices=[(relation, relation) for relation in PATIENT_RELATIONS],
        validators=[DataRequired()],
    )
    submit = SubmitField("Save profile")


class BloodRequestForm(FlaskForm):
    units = SelectField(
        "Units needed",
        choices=[(str(i), f"{i} unit{'s' if i > 1 else ''}") for i in range(1, 11)],
        default="1",
        validators=[DataRequired()],
    )
    urgency = SelectField(
        "Urgency",
        choices=[(level, f"{URGENCY_META[level]['label']} — {URGENCY_META[level]['description']}") for level in URGENCY_LEVELS],
        default="urgent",
        validators=[DataRequired()],
    )
    hospital_name = StringField(
        "Hospital name", validators=[DataRequired(), Length(min=3, max=150)]
    )
    hospital_address = StringField(
        "Hospital address", validators=[Optional(), Length(max=255)]
    )
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=80)])
    needed_by = DateField(
        "Needed by", validators=[DataRequired(), validate_needed_by]
    )
    contact_phone = StringField(
        "Contact phone", validators=[DataRequired(), Length(max=24), validate_phone]
    )
    message = TextAreaField(
        "Message to donor",
        validators=[Optional(), Length(max=2000)],
        description="Include the ward, patient reference or any instructions the donor needs.",
    )
    confirm_info = BooleanField(
        "I confirm these details are accurate and I will use the donor's details responsibly",
        validators=[DataRequired(message="Please confirm the request details.")],
    )
    submit = SubmitField("Send blood request")


class ReportForm(FlaskForm):
    reason = SelectField(
        "Reason",
        choices=[(reason, reason) for reason in REPORT_REASONS],
        validators=[DataRequired()],
    )
    description = TextAreaField(
        "What happened?",
        validators=[DataRequired(), Length(min=20, max=2000)],
        description="Give the administrator enough context to investigate. Do not include passwords.",
    )
    submit = SubmitField("Submit report")


class AdminReportForm(FlaskForm):
    status = SelectField(
        "Decision",
        choices=[("resolved", "Resolved"), ("dismissed", "Dismissed")],
        validators=[DataRequired()],
    )
    admin_note = TextAreaField(
        "Internal note", validators=[DataRequired(), Length(min=5, max=2000)]
    )
    submit = SubmitField("Save decision")
