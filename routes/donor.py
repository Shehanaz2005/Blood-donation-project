"""Donor dashboard, profile, availability and request responses."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import case, func

from extensions import db
from forms.donor import AvailabilityForm, DonorProfileForm
from models import BloodRequest
from services.requests import DomainError, expire_overdue_requests, respond_to_request
from services.stats import donor_stats
from utils.constants import REQUEST_STATUSES
from utils.helpers import normalise_phone, role_required, wants_json

donor_bp = Blueprint("donor", __name__)


def _profile_or_redirect():
    profile = current_user.donor_profile
    if not profile:
        flash("Your donor profile is incomplete. Please contact support.", "danger")
    return profile


def _incoming_requests(limit: int | None = None):
    stmt = (
        BloodRequest.query.filter_by(donor_id=current_user.id)
        .order_by(
            case(
                (BloodRequest.status == "pending", 0),
                (BloodRequest.status == "accepted", 1),
                else_=2,
            ),
            BloodRequest.created_at.desc(),
        )
    )
    return stmt.limit(limit).all() if limit else stmt.all()


@donor_bp.get("/dashboard")
@login_required
@role_required("donor")
def dashboard():
    profile = _profile_or_redirect()
    if not profile:
        return redirect(url_for("main.home"))

    expire_overdue_requests()
    stats = donor_stats(current_user)
    pending = (
        BloodRequest.query.filter_by(donor_id=current_user.id, status="pending")
        .order_by(BloodRequest.created_at.asc())
        .limit(5)
        .all()
    )
    accepted = (
        BloodRequest.query.filter_by(donor_id=current_user.id, status="accepted")
        .order_by(BloodRequest.created_at.desc())
        .limit(3)
        .all()
    )
    history = (
        BloodRequest.query.filter_by(donor_id=current_user.id)
        .order_by(BloodRequest.created_at.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "donor/dashboard.html",
        profile=profile,
        stats=stats,
        pending_requests=pending,
        accepted_requests=accepted,
        history=history,
        availability_form=AvailabilityForm(available=profile.is_available),
    )


# ----------------------------------------------------------------------
# Profile
# ----------------------------------------------------------------------
@donor_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("donor")
def profile_edit():
    profile = _profile_or_redirect()
    if not profile:
        return redirect(url_for("main.home"))

    form = DonorProfileForm(obj=profile)
    if request.method == "GET":
        form.full_name.data = current_user.full_name
        form.email.data = current_user.email
        form.phone.data = current_user.phone

    if form.validate_on_submit():
        current_user.full_name = form.full_name.data.strip()
        current_user.email = form.email.data.strip().lower()
        current_user.phone = normalise_phone(form.phone.data)
        profile.blood_group = form.blood_group.data
        profile.date_of_birth = form.date_of_birth.data
        profile.gender = form.gender.data
        profile.weight_kg = form.weight_kg.data
        profile.city = form.city.data.strip().title()
        profile.address = form.address.data.strip()
        profile.last_donation_date = form.last_donation_date.data
        profile.share_contact = bool(form.share_contact.data)
        profile.bio = (form.bio.data or "").strip() or None
        db.session.commit()
        flash("Your donor profile has been updated.", "success")
        return redirect(url_for("donor.profile_edit"))

    return render_template("donor/profile.html", form=form, profile=profile)


@donor_bp.post("/availability")
@login_required
@role_required("donor")
def availability():
    profile = _profile_or_redirect()
    if not profile:
        if wants_json():
            return jsonify({"ok": False, "message": "Donor profile not found."}), 404
        return redirect(url_for("main.home"))

    payload = request.get_json(silent=True) or {}
    if "available" in payload:
        desired = bool(payload.get("available"))
    else:
        form = AvailabilityForm()
        desired = bool(form.available.data)

    message = ""
    if desired and not profile.is_eligible:
        desired = False
        message = profile.eligibility_reasons[-1] if profile.eligibility_reasons else "You are not eligible yet."
        flash(f"You cannot switch to available yet: {message}", "warning")
    else:
        profile.is_available = desired
        db.session.commit()
        flash(
            "You are now visible as available to receivers."
            if desired
            else "You are now marked as unavailable.",
            "success",
        )

    if wants_json():
        return jsonify(
            {
                "ok": True,
                "is_available": profile.is_available,
                "can_accept_requests": profile.can_accept_requests,
                "message": message,
                "url": url_for("donor.dashboard"),
            }
        )
    return redirect(url_for("donor.dashboard"))


# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------
@donor_bp.get("/requests")
@login_required
@role_required("donor")
def requests_list():
    expire_overdue_requests()
    status = (request.args.get("status") or "all").strip().lower()
    if status not in REQUEST_STATUSES and status != "all":
        status = "all"
    page = max(request.args.get("page", 1, type=int), 1)

    query = BloodRequest.query.filter_by(donor_id=current_user.id)
    if status != "all":
        query = query.filter_by(status=status)
    query = query.order_by(BloodRequest.created_at.desc())
    pagination = query.paginate(page=page, per_page=10, error_out=False)

    counts = dict(
        db.session.query(BloodRequest.status, func.count(BloodRequest.id))
        .filter(BloodRequest.donor_id == current_user.id)
        .group_by(BloodRequest.status)
        .all()
    )
    counts["all"] = sum(counts.values())

    return render_template(
        "donor/requests.html",
        pagination=pagination,
        current_status=status,
        statuses=REQUEST_STATUSES,
        counts=counts,
    )


@donor_bp.get("/requests/<int:request_id>")
@login_required
@role_required("donor")
def request_detail(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request or blood_request.donor_id != current_user.id:
        abort(404)
    return render_template(
        "donor/request_detail.html",
        blood_request=blood_request,
        profile=current_user.donor_profile,
    )


@donor_bp.post("/requests/<int:request_id>/respond")
@login_required
@role_required("donor")
def respond(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request or blood_request.donor_id != current_user.id:
        abort(404)

    action = (request.form.get("action") or "").strip().lower()
    note = request.form.get("note", "")
    try:
        respond_to_request(blood_request, current_user, action, note)
    except DomainError as exc:
        db.session.rollback()
        flash(exc.message, "danger")
    else:
        flash(
            "Request accepted. The receiver can now see your response and contact details (if you share them)."
            if action == "accept"
            else "Request declined. The receiver has been notified.",
            "success" if action == "accept" else "info",
        )
    return redirect(url_for("donor.request_detail", request_id=request_id))
