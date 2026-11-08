"""Registration, login and logout."""
from __future__ import annotations

from datetime import date, timedelta

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db, limiter
from forms.auth import DonorRegistrationForm, LoginForm, ReceiverRegistrationForm
from models import AdminProfile, DonorProfile, ReceiverProfile, User
from services.notifications import notify, notify_many
from utils.helpers import (
    dashboard_url_for,
    normalise_phone,
    safe_next_url,
    utcnow,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _redirect_authenticated():
    if current_user.is_authenticated:
        return redirect(dashboard_url_for(current_user))
    return None


# ----------------------------------------------------------------------
# Donor registration
# ----------------------------------------------------------------------
@auth_bp.route("/register/donor", methods=["GET", "POST"])
@limiter.limit("12 per hour", methods=["POST"])
def register_donor():
    already = _redirect_authenticated()
    if already:
        return already

    form = DonorRegistrationForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip().lower(),
            phone=normalise_phone(form.phone.data),
            role="donor",
            is_active=True,
        )
        user.set_password(form.password.data)

        cooldown = current_app_config_days()
        last_donation = form.last_donation_date.data
        in_cooldown = bool(last_donation and last_donation + timedelta(days=cooldown) > date.today())

        donor = DonorProfile(
            blood_group=form.blood_group.data,
            date_of_birth=form.date_of_birth.data,
            gender=form.gender.data,
            weight_kg=form.weight_kg.data,
            city=form.city.data.strip().title(),
            address=form.address.data.strip(),
            last_donation_date=last_donation,
            is_available=not in_cooldown,
            is_verified=False,
            share_contact=bool(form.share_contact.data),
            total_donations=0,
        )
        user.donor_profile = donor
        db.session.add(user)
        db.session.flush()

        notify(
            user,
            "Welcome to Blood Connect",
            "Your donor account is ready. An administrator will verify your profile shortly. "
            "Once verified, you can accept requests from receivers near you.",
            category="account",
            link=url_for("donor.dashboard"),
        )
        admins = User.query.filter_by(role="admin", is_active=True).all()
        notify_many(
            admins,
            "New donor awaiting verification",
            f"{user.full_name} ({donor.blood_group}, {donor.city}) has registered as a donor.",
            category="verification",
            link=url_for("admin.donors", verified="0"),
        )
        db.session.commit()

        login_user(user, remember=False)
        if in_cooldown:
            flash(
                "Your account was created, but you are inside the 90-day donation cooldown. "
                "We will mark you available once you are eligible again.",
                "warning",
            )
        else:
            flash(
                "Welcome to Blood Connect! Your donor profile is pending administrator verification.",
                "success",
            )
        return redirect(url_for("donor.dashboard"))

    return render_template("auth/register_donor.html", form=form)


def current_app_config_days() -> int:
    from flask import current_app

    return int(current_app.config.get("DONATION_COOLDOWN_DAYS", 90))


# ----------------------------------------------------------------------
# Receiver registration
# ----------------------------------------------------------------------
@auth_bp.route("/register/receiver", methods=["GET", "POST"])
@limiter.limit("12 per hour", methods=["POST"])
def register_receiver():
    already = _redirect_authenticated()
    if already:
        return already

    form = ReceiverRegistrationForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip().lower(),
            phone=normalise_phone(form.phone.data),
            role="receiver",
            is_active=True,
        )
        user.set_password(form.password.data)
        user.receiver_profile = ReceiverProfile(
            city=form.city.data.strip().title(),
            address=form.address.data.strip(),
            patient_relation=form.patient_relation.data,
        )
        db.session.add(user)
        db.session.flush()
        notify(
            user,
            "Welcome to Blood Connect",
            "Your receiver account is ready. Search verified donors by blood group and city, "
            "then send a request with your hospital details.",
            category="account",
            link=url_for("main.find_donors"),
        )
        db.session.commit()

        login_user(user, remember=False)
        flash("Your receiver account is ready. Start by searching for available donors.", "success")
        return redirect(url_for("receiver.dashboard"))

    return render_template("auth/register_receiver.html", form=form)


# ----------------------------------------------------------------------
# Login / logout
# ----------------------------------------------------------------------
def _authenticate(form: LoginForm, *, admin_only: bool = False):
    email = (form.email.data or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(form.password.data):
        flash("Invalid email or password. Please check your details and try again.", "danger")
        return None
    if not user.is_active:
        flash(
            "This account has been disabled. Please contact support if you believe this is a mistake.",
            "danger",
        )
        return None
    if admin_only and user.role != "admin":
        flash("Administrator credentials are required to access the admin console.", "danger")
        return None
    user.touch_login()
    db.session.commit()
    login_user(user, remember=bool(form.remember.data))
    return user


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@limiter.limit("40 per hour", methods=["POST"])
def login():
    already = _redirect_authenticated()
    if already:
        return already

    form = LoginForm()
    if form.validate_on_submit():
        user = _authenticate(form)
        if user:
            next_url = safe_next_url(request.args.get("next") or request.form.get("next"))
            flash(f"Welcome back, {user.display_name}.", "success")
            if next_url:
                return redirect(next_url)
            return redirect(dashboard_url_for(user))

    return render_template("auth/login.html", form=form, next_url=request.args.get("next", ""))


@auth_bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@limiter.limit("40 per hour", methods=["POST"])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        logout_user()
        flash("You were signed out because the admin console requires an administrator account.", "info")

    form = LoginForm()
    if form.validate_on_submit():
        user = _authenticate(form, admin_only=True)
        if user:
            flash("Administrator signed in.", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template("auth/admin_login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.home"))
