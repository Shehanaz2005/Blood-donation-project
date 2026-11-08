"""Versioned JSON API used by the donor search UI and external clients.

Authentication uses the same secure session cookie as the HTML app, so
unsafe requests must include the ``X-CSRFToken`` header (the value is
rendered into ``<meta name="csrf-token">``). This keeps the API free of
long-lived bearer tokens for a same-origin application.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from extensions import db, limiter
from models import BloodRequest, DonorProfile, Notification, User
from services.donors import (
    donor_cities,
    donor_count_by_group,
    parse_search_filters,
    search_donors,
    serialise_donor_card,
    serialise_donor_detail,
)
from services.notifications import mark_all_read
from services.requests import (
    DomainError,
    cancel_request,
    complete_request,
    create_request,
    respond_to_request,
)
from services.stats import admin_stats, public_stats
from utils.constants import (
    BLOOD_GROUPS,
    compatible_donor_groups,
)
from utils.helpers import role_required

api_bp = Blueprint("api", __name__)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def ok(data=None, meta=None, status: int = 200):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def fail(code: str, message: str, status: int = 400, field: str | None = None):
    error = {"code": code, "message": message}
    if field:
        error["field"] = field
    return jsonify({"ok": False, "error": error}), status


def pagination_meta(pagination, endpoint: str):
    args = request.args.to_dict(flat=True)

    def page_url(page: int) -> str:
        params = dict(args)
        params["page"] = page
        return url_for(endpoint, **params)

    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "total": pagination.total,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
        "next_page": page_url(pagination.next_num) if pagination.has_next else None,
        "prev_page": page_url(pagination.prev_num) if pagination.has_prev else None,
    }


def serialise_request(blood_request: BloodRequest, viewer) -> dict:
    is_receiver_owner = viewer.id == blood_request.receiver_id
    is_donor = viewer.id == blood_request.donor_id
    is_admin = viewer.role == "admin"

    donor_profile = blood_request.donor.donor_profile
    donor_contact_allowed = is_admin or (
        is_receiver_owner and blood_request.donor_contact_available and bool(donor_profile and donor_profile.share_contact)
    )
    receiver_contact_allowed = is_admin or is_receiver_owner or (
        is_donor and blood_request.status in ("accepted", "completed")
    )

    return {
        "id": blood_request.id,
        "reference": blood_request.reference,
        "status": blood_request.status,
        "status_label": blood_request.status_label,
        "blood_group": blood_request.blood_group,
        "units": blood_request.units,
        "urgency": blood_request.urgency,
        "hospital_name": blood_request.hospital_name,
        "hospital_address": blood_request.hospital_address,
        "city": blood_request.city,
        "needed_by": blood_request.needed_by.isoformat() if blood_request.needed_by else None,
        "message": blood_request.message,
        "donor_response": blood_request.donor_response,
        "created_at": blood_request.created_at.isoformat() if blood_request.created_at else None,
        "responded_at": blood_request.responded_at.isoformat() if blood_request.responded_at else None,
        "completed_at": blood_request.completed_at.isoformat() if blood_request.completed_at else None,
        "is_overdue": blood_request.is_overdue,
        "donor": {
            "id": blood_request.donor.id,
            "name": blood_request.donor.full_name,
            "phone": blood_request.donor.phone if donor_contact_allowed else None,
            "contact_visible": donor_contact_allowed,
            "profile_url": url_for("main.donor_profile", donor_id=donor_profile.id)
            if donor_profile
            else None,
        },
        "receiver": {
            "id": blood_request.receiver.id,
            "name": blood_request.receiver.full_name,
            "phone": blood_request.receiver.phone if receiver_contact_allowed else None,
            "contact_visible": receiver_contact_allowed,
        },
    }


def _scoped_request(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request:
        return None
    if current_user.role == "admin":
        return blood_request
    if current_user.id in (blood_request.receiver_id, blood_request.donor_id):
        return blood_request
    return None


# ----------------------------------------------------------------------
# Public directory
# ----------------------------------------------------------------------
@api_bp.get("/donors")
@limiter.limit("120 per minute")
def list_donors():
    filters = parse_search_filters(request.args)
    per_page = request.args.get("per_page", type=int) or 9
    pagination = search_donors(filters, per_page=per_page)
    data = [serialise_donor_card(donor, current_user) for donor in pagination.items]
    meta = pagination_meta(pagination, "api.list_donors")
    meta["filters"] = filters
    return ok(data, meta)


@api_bp.get("/donors/cities")
@limiter.limit("120 per minute")
def list_cities():
    return ok(donor_cities())


@api_bp.get("/donors/<int:donor_id>")
def donor_detail(donor_id: int):
    donor = db.session.get(DonorProfile, donor_id)
    if not donor or not donor.user or not donor.user.is_active:
        return fail("not_found", "Donor not found.", 404)
    return ok(serialise_donor_detail(donor, current_user))


@api_bp.get("/blood-groups")
def blood_groups():
    return ok(
        [
            {
                "group": group,
                "can_donate_to": list(compatible_donor_groups(group)),
                "donors": donor_count_by_group().get(group, 0),
            }
            for group in BLOOD_GROUPS
        ]
    )


@api_bp.get("/stats")
@limiter.limit("60 per minute")
def stats():
    return ok(public_stats())


# ----------------------------------------------------------------------
# Current user
# ----------------------------------------------------------------------
@api_bp.get("/me")
@login_required
def me():
    profile = current_user.profile
    payload = {
        "id": current_user.id,
        "name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "unread_notifications": current_user.unread_notifications,
    }
    if current_user.role == "donor" and profile:
        payload["donor"] = {
            "blood_group": profile.blood_group,
            "city": profile.city,
            "is_available": profile.is_available,
            "is_verified": profile.is_verified,
            "is_eligible": profile.is_eligible,
            "total_donations": profile.total_donations,
        }
    return ok(payload)


@api_bp.patch("/donor/availability")
@api_bp.post("/donor/availability")
@login_required
@role_required("donor")
def set_availability():
    donor = current_user.donor_profile
    if not donor:
        return fail("profile_missing", "Donor profile not found.", 404)
    payload = request.get_json(silent=True) or {}
    if "available" not in payload:
        return fail("validation_error", "Provide an 'available' boolean.", 422, "available")
    available = bool(payload["available"])
    if available and not donor.is_eligible:
        return fail(
            "not_eligible",
            donor.eligibility_reasons[-1]
            if donor.eligibility_reasons
            else "You are not eligible to donate yet.",
            409,
            "available",
        )
    donor.is_available = available
    db.session.commit()
    return ok(
        {
            "is_available": donor.is_available,
            "can_accept_requests": donor.can_accept_requests,
            "eligibility_reasons": donor.eligibility_reasons,
        }
    )


# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------
@api_bp.get("/requests")
@login_required
def list_requests():
    status = (request.args.get("status") or "all").lower()
    page = max(request.args.get("page", 1, type=int), 1)
    if current_user.role == "admin":
        stmt = select(BloodRequest)
    elif current_user.role == "receiver":
        stmt = select(BloodRequest).where(BloodRequest.receiver_id == current_user.id)
    elif current_user.role == "donor":
        stmt = select(BloodRequest).where(BloodRequest.donor_id == current_user.id)
    else:
        return fail("forbidden", "This account cannot view requests.", 403)
    if status != "all":
        stmt = stmt.where(BloodRequest.status == status)
    stmt = stmt.order_by(BloodRequest.created_at.desc())
    pagination = db.paginate(stmt, page=page, per_page=10, error_out=False)
    return ok(
        [serialise_request(item, current_user) for item in pagination.items],
        pagination_meta(pagination, "api.list_requests"),
    )


@api_bp.post("/requests")
@login_required
@role_required("receiver")
def create_request_endpoint():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return fail("invalid_json", "Send a JSON object.", 400)
    donor_id = payload.get("donor_id")
    try:
        donor_id = int(donor_id)
    except (TypeError, ValueError):
        return fail("validation_error", "A valid donor_id is required.", 422, "donor_id")
    donor_user = db.session.get(User, donor_id)
    if not donor_user or donor_user.role != "donor":
        return fail("donor_not_found", "Donor not found.", 404, "donor_id")
    try:
        blood_request = create_request(current_user, donor_user, payload)
    except DomainError as exc:
        db.session.rollback()
        return fail("validation_error", exc.message, exc.status_code, exc.field)
    return ok(serialise_request(blood_request, current_user), status=201)


@api_bp.get("/requests/<int:request_id>")
@login_required
def request_detail_endpoint(request_id: int):
    blood_request = _scoped_request(request_id)
    if not blood_request:
        return fail("not_found", "Request not found.", 404)
    return ok(serialise_request(blood_request, current_user))


@api_bp.route("/requests/<int:request_id>/status", methods=["POST", "PATCH"])
@login_required
def update_request_status(request_id: int):
    blood_request = _scoped_request(request_id)
    if not blood_request:
        return fail("not_found", "Request not found.", 404)

    payload = request.get_json(silent=True) or request.form
    action = (payload.get("action") or "").strip().lower()
    note = payload.get("note", "")
    try:
        if action in {"accept", "reject", "decline"}:
            if current_user.id != blood_request.donor_id:
                return fail("forbidden", "Only the requested donor can accept or decline.", 403)
            blood_request = respond_to_request(
                blood_request, current_user, "reject" if action == "decline" else action, note
            )
        elif action == "cancel":
            blood_request = cancel_request(blood_request, current_user, note)
        elif action == "complete":
            blood_request = complete_request(blood_request, current_user)
        else:
            return fail(
                "validation_error",
                "action must be one of: accept, reject, cancel, complete.",
                422,
                "action",
            )
    except DomainError as exc:
        db.session.rollback()
        return fail("conflict", exc.message, exc.status_code, exc.field)
    return ok(serialise_request(blood_request, current_user))


# ----------------------------------------------------------------------
# Notifications
# ----------------------------------------------------------------------
@api_bp.get("/notifications")
@login_required
def list_notifications():
    unread_only = (request.args.get("unread") or "").lower() in {"1", "true", "yes"}
    query = current_user.notifications
    if unread_only:
        query = query.filter_by(is_read=False)
    items = query.limit(50).all()
    return ok(
        [
            {
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "category": item.category,
                "link": item.link,
                "is_read": item.is_read,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        {"unread": current_user.unread_notifications},
    )


@api_bp.post("/notifications/read-all")
@login_required
def read_all_notifications():
    count = mark_all_read(current_user, commit=False)
    db.session.commit()
    return ok({"updated": count})


@api_bp.post("/notifications/<int:notification_id>/read")
@login_required
def read_notification(notification_id: int):
    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != current_user.id:
        return fail("not_found", "Notification not found.", 404)
    notification.is_read = True
    db.session.commit()
    return ok({"id": notification.id, "is_read": True})


# ----------------------------------------------------------------------
# Admin
# ----------------------------------------------------------------------
@api_bp.get("/admin/stats")
@login_required
@role_required("admin")
def admin_stats_endpoint():
    stats = admin_stats()
    serialisable = {
        key: value
        for key, value in stats.items()
        if key not in {"recent_requests", "pending_donors"}
    }
    return ok(serialisable)
