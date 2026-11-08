"""Receiver dashboard, donor requests and profile."""
from __future__ import annotations

from datetime import date, timedelta

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import case, func, select

from extensions import db
from forms.receiver import BloodRequestForm, ReceiverProfileForm
from models import BloodRequest, DonorProfile, User
from services.donors import serialise_donor_card
from services.requests import (
    DomainError,
    cancel_request,
    complete_request,
    create_request,
    expire_overdue_requests,
)
from services.stats import receiver_stats
from utils.constants import ACTIVE_REQUEST_STATUSES, REQUEST_STATUSES
from utils.helpers import normalise_phone, role_required

receiver_bp = Blueprint("receiver", __name__)


def _profile_or_redirect():
    profile = current_user.receiver_profile
    if not profile:
        flash("Your receiver profile is incomplete. Please contact support.", "danger")
    return profile


@receiver_bp.get("/dashboard")
@login_required
@role_required("receiver")
def dashboard():
    profile = _profile_or_redirect()
    if not profile:
        return redirect(url_for("main.home"))

    expire_overdue_requests()
    stats = receiver_stats(current_user)
    active_requests = (
        BloodRequest.query.filter_by(receiver_id=current_user.id)
        .filter(BloodRequest.status.in_(ACTIVE_REQUEST_STATUSES))
        .order_by(BloodRequest.created_at.desc())
        .limit(5)
        .all()
    )
    recent = (
        BloodRequest.query.filter_by(receiver_id=current_user.id)
        .order_by(BloodRequest.created_at.desc())
        .limit(6)
        .all()
    )
    suggested = db.session.scalars(
        select(DonorProfile)
        .join(User, User.id == DonorProfile.user_id)
        .where(
            User.is_active.is_(True),
            DonorProfile.is_verified.is_(True),
            DonorProfile.is_available.is_(True),
        )
        .order_by(
            case((DonorProfile.city == profile.city, 0), else_=1),
            DonorProfile.total_donations.desc(),
        )
        .limit(3)
    ).all()

    return render_template(
        "receiver/dashboard.html",
        profile=profile,
        stats=stats,
        active_requests=active_requests,
        recent_requests=recent,
        suggested_donors=[serialise_donor_card(d, current_user) for d in suggested],
    )


# ----------------------------------------------------------------------
# Profile
# ----------------------------------------------------------------------
@receiver_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("receiver")
def profile_edit():
    profile = _profile_or_redirect()
    if not profile:
        return redirect(url_for("main.home"))

    form = ReceiverProfileForm(obj=profile)
    if request.method == "GET":
        form.full_name.data = current_user.full_name
        form.email.data = current_user.email
        form.phone.data = current_user.phone

    if form.validate_on_submit():
        current_user.full_name = form.full_name.data.strip()
        current_user.email = form.email.data.strip().lower()
        current_user.phone = normalise_phone(form.phone.data)
        profile.city = form.city.data.strip().title()
        profile.address = form.address.data.strip()
        profile.preferred_hospital = (form.preferred_hospital.data or "").strip() or None
        profile.patient_relation = form.patient_relation.data
        db.session.commit()
        flash("Your receiver profile has been updated.", "success")
        return redirect(url_for("receiver.profile_edit"))

    return render_template("receiver/profile.html", form=form, profile=profile)


# ----------------------------------------------------------------------
# Create / track requests
# ----------------------------------------------------------------------
@receiver_bp.route("/requests/new/<int:donor_id>", methods=["GET", "POST"])
@login_required
@role_required("receiver")
def new_request(donor_id: int):
    donor = db.session.get(DonorProfile, donor_id)
    if not donor or not donor.user or not donor.user.is_active:
        abort(404)
    if not donor.is_verified or not donor.is_available or not donor.is_eligible:
        flash(
            "That donor is not currently accepting requests. Pick another available, verified donor.",
            "warning",
        )
        return redirect(url_for("main.donor_profile", donor_id=donor.id))

    profile = _profile_or_redirect()
    form = BloodRequestForm()
    if request.method == "GET":
        form.city.data = profile.city if profile else ""
        form.contact_phone.data = current_user.phone
        form.needed_by.data = date.today() + timedelta(days=1)
        form.hospital_name.data = (profile.preferred_hospital if profile else "") or ""
        form.units.data = "1"
        form.urgency.data = "urgent"

    if form.validate_on_submit():
        try:
            blood_request = create_request(
                current_user,
                donor.user,
                {
                    "units": form.units.data,
                    "urgency": form.urgency.data,
                    "hospital_name": form.hospital_name.data,
                    "hospital_address": form.hospital_address.data,
                    "city": form.city.data,
                    "needed_by": form.needed_by.data,
                    "contact_phone": form.contact_phone.data,
                    "message": form.message.data,
                },
            )
        except DomainError as exc:
            db.session.rollback()
            flash(exc.message, "danger")
        else:
            flash(
                f"Request {blood_request.reference} sent to {donor.user.full_name}. "
                "You will be notified here and in your dashboard when they respond.",
                "success",
            )
            return redirect(
                url_for("receiver.request_detail", request_id=blood_request.id)
            )

    return render_template(
        "receiver/new_request.html",
        form=form,
        donor=donor,
        donor_data=serialise_donor_card(donor, current_user),
    )


@receiver_bp.get("/requests")
@login_required
@role_required("receiver")
def requests_list():
    expire_overdue_requests()
    status = (request.args.get("status") or "all").strip().lower()
    if status not in REQUEST_STATUSES and status != "all":
        status = "all"
    page = max(request.args.get("page", 1, type=int), 1)

    query = BloodRequest.query.filter_by(receiver_id=current_user.id)
    if status != "all":
        query = query.filter_by(status=status)
    pagination = query.order_by(BloodRequest.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    counts = dict(
        db.session.query(BloodRequest.status, func.count(BloodRequest.id))
        .filter(BloodRequest.receiver_id == current_user.id)
        .group_by(BloodRequest.status)
        .all()
    )
    counts["all"] = sum(counts.values())
    return render_template(
        "receiver/requests.html",
        pagination=pagination,
        current_status=status,
        statuses=REQUEST_STATUSES,
        counts=counts,
    )


@receiver_bp.get("/requests/<int:request_id>")
@login_required
@role_required("receiver")
def request_detail(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request or blood_request.receiver_id != current_user.id:
        abort(404)
    return render_template(
        "receiver/request_detail.html",
        blood_request=blood_request,
        profile=current_user.receiver_profile,
    )


@receiver_bp.post("/requests/<int:request_id>/cancel")
@login_required
@role_required("receiver")
def cancel(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request or blood_request.receiver_id != current_user.id:
        abort(404)
    try:
        cancel_request(blood_request, current_user, request.form.get("reason", ""))
    except DomainError as exc:
        db.session.rollback()
        flash(exc.message, "danger")
    else:
        flash(f"Request {blood_request.reference} has been cancelled.", "info")
    return redirect(url_for("receiver.request_detail", request_id=request_id))


@receiver_bp.post("/requests/<int:request_id>/complete")
@login_required
@role_required("receiver")
def complete(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request or blood_request.receiver_id != current_user.id:
        abort(404)
    try:
        complete_request(blood_request, current_user)
    except DomainError as exc:
        db.session.rollback()
        flash(exc.message, "danger")
    else:
        flash(
            "Donation marked complete. Thank you for confirming — the donor's record has been updated.",
            "success",
        )
    return redirect(url_for("receiver.request_detail", request_id=request_id))
