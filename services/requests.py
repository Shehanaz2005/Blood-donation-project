"""Blood request lifecycle — shared by HTML routes and the JSON API.

Every state transition lives here so permissions, notifications and
side-effects behave identically regardless of the entry point.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from flask import url_for
from sqlalchemy import select

from extensions import db
from models import BloodRequest, DonorProfile, Notification, User
from services.notifications import notify
from utils.constants import (
    ACTIVE_REQUEST_STATUSES,
    REQUEST_ACCEPTED,
    REQUEST_CANCELLED,
    REQUEST_COMPLETED,
    REQUEST_PENDING,
    REQUEST_REJECTED,
    URGENCY_LEVELS,
)
from utils.helpers import generate_reference, is_valid_phone, utcnow


class DomainError(Exception):
    """A user-correctable business rule violation."""

    def __init__(self, message: str, status_code: int = 400, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.field = field


def _relative(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _clean_text(value, field: str, *, min_length: int = 1, max_length: int = 2000, required: bool = True) -> str:
    text = (value or "").strip()
    if required and len(text) < min_length:
        raise DomainError(f"{field} is required.", field=field)
    if len(text) > max_length:
        raise DomainError(f"{field} must be {max_length} characters or fewer.", field=field)
    return text


def create_request(receiver, donor_user, data: dict) -> BloodRequest:
    """Create a request from a receiver to a verified, eligible donor."""
    if not receiver or receiver.role != "receiver":
        raise DomainError("Only receiver accounts can create blood requests.", 403)
    if not donor_user or donor_user.role != "donor":
        raise DomainError("This account is not a donor.", 404)

    donor = donor_user.donor_profile
    if not donor:
        raise DomainError("This donor has not completed their profile.", 400)
    if donor.user_id == receiver.id:
        raise DomainError("You cannot send a request to yourself.", 400)
    if not donor.is_verified:
        raise DomainError("This donor is still awaiting verification. Please choose a verified donor.", 400)
    if not donor.is_available:
        raise DomainError("This donor is currently marked unavailable.", 400)
    if not donor.is_eligible:
        reason = donor.eligibility_reasons[-1] if donor.eligibility_reasons else "This donor is not currently eligible."
        raise DomainError(reason, 400)

    duplicate = db.session.scalar(
        select(BloodRequest.id).where(
            BloodRequest.receiver_id == receiver.id,
            BloodRequest.donor_id == donor_user.id,
            BloodRequest.status.in_(ACTIVE_REQUEST_STATUSES),
        )
    )
    if duplicate:
        raise DomainError(
            "You already have an active request with this donor. Please track the existing request instead.",
            409,
        )

    try:
        units = int(data.get("units", 1))
    except (TypeError, ValueError):
        raise DomainError("Units must be a whole number.", field="units")
    if units < 1 or units > 10:
        raise DomainError("Units must be between 1 and 10.", field="units")

    urgency = (data.get("urgency") or "urgent").strip().lower()
    if urgency not in URGENCY_LEVELS:
        raise DomainError("Choose a valid urgency level.", field="urgency")

    hospital_name = _clean_text(data.get("hospital_name"), "Hospital name", max_length=150)
    hospital_address = _clean_text(
        data.get("hospital_address"), "Hospital address", max_length=255, required=False
    )
    city = _clean_text(data.get("city"), "City", min_length=2, max_length=80)
    contact_phone = _clean_text(data.get("contact_phone"), "Contact phone", max_length=24)
    if not is_valid_phone(contact_phone):
        raise DomainError("Enter a valid contact phone number.", field="contact_phone")
    message = _clean_text(data.get("message"), "Message", max_length=2000, required=False)

    needed_by = data.get("needed_by")
    if isinstance(needed_by, str):
        try:
            needed_by = date.fromisoformat(needed_by)
        except ValueError:
            raise DomainError("Enter a valid needed-by date.", field="needed_by")
    if needed_by and needed_by < date.today():
        raise DomainError("The needed-by date cannot be in the past.", field="needed_by")

    blood_request = BloodRequest(
        reference=generate_reference(),
        receiver_id=receiver.id,
        donor_id=donor_user.id,
        blood_group=donor.blood_group,
        units=units,
        urgency=urgency,
        hospital_name=hospital_name,
        hospital_address=hospital_address,
        city=city,
        needed_by=needed_by,
        contact_phone=contact_phone,
        message=message,
        status=REQUEST_PENDING,
    )
    db.session.add(blood_request)
    db.session.flush()
    notify(
        donor_user,
        "New blood request received",
        f"{receiver.full_name} needs {units} unit(s) of {donor.blood_group} blood at "
        f"{hospital_name}, {city}. Review it and respond when you can.",
        category="request",
        link=_relative(url_for("donor.request_detail", request_id=blood_request.id)),
    )
    db.session.commit()
    return blood_request


def respond_to_request(blood_request: BloodRequest, donor_user, action: str, note: str = "") -> BloodRequest:
    if not donor_user or blood_request.donor_id != donor_user.id:
        raise DomainError("You do not have permission to respond to this request.", 403)
    if blood_request.status != REQUEST_PENDING:
        raise DomainError("This request has already been handled.", 409)

    note = _clean_text(note, "Response note", max_length=1000, required=False)
    donor = donor_user.donor_profile
    action = (action or "").lower()

    if action == "accept":
        if not donor or not donor.is_verified:
            raise DomainError(
                "Your donor profile must be verified by an administrator before you can accept requests.",
                403,
            )
        if not donor.is_available:
            raise DomainError(
                "Set yourself as available before accepting a request.", 400
            )
        if not donor.is_eligible:
            raise DomainError(
                donor.eligibility_reasons[-1] if donor.eligibility_reasons else "You are not eligible to donate yet.",
                400,
            )
        blood_request.status = REQUEST_ACCEPTED
        title = "Your blood request was accepted"
        body = (
            f"{donor_user.full_name} accepted your request for {blood_request.units} unit(s) of "
            f"{blood_request.blood_group} blood. See the request page for the next steps."
        )
    elif action == "reject":
        blood_request.status = REQUEST_REJECTED
        title = "Your blood request was declined"
        body = (
            f"{donor_user.full_name} is unable to donate for request {blood_request.reference}. "
            "You can search for another available donor."
        )
    else:
        raise DomainError("Choose either accept or decline.", field="action")

    blood_request.donor_response = note or None
    blood_request.responded_at = utcnow()
    notify(
        blood_request.receiver,
        title,
        body,
        category="request",
        link=_relative(url_for("receiver.request_detail", request_id=blood_request.id)),
    )
    db.session.commit()
    return blood_request


def cancel_request(blood_request: BloodRequest, actor, reason: str = "") -> BloodRequest:
    is_owner = actor.id == blood_request.receiver_id
    is_admin = getattr(actor, "role", "") == "admin"
    if not (is_owner or is_admin):
        raise DomainError("You do not have permission to cancel this request.", 403)
    if blood_request.status not in ACTIVE_REQUEST_STATUSES:
        raise DomainError("Only pending or accepted requests can be cancelled.", 409)

    blood_request.status = REQUEST_CANCELLED
    blood_request.cancelled_at = utcnow()
    if reason:
        blood_request.donor_response = _clean_text(reason, "Cancellation note", max_length=1000, required=False)

    notify(
        blood_request.donor,
        "A blood request was cancelled",
        f"Request {blood_request.reference} from {blood_request.receiver.full_name} was cancelled.",
        category="request",
        link=_relative(url_for("donor.request_detail", request_id=blood_request.id)),
    )
    if is_admin and not is_owner:
        notify(
            blood_request.receiver,
            "Your request was cancelled by an administrator",
            f"Request {blood_request.reference} was cancelled after an administrative review.",
            category="request",
            link=_relative(url_for("receiver.request_detail", request_id=blood_request.id)),
        )
    db.session.commit()
    return blood_request


def complete_request(blood_request: BloodRequest, actor) -> BloodRequest:
    is_owner = actor.id == blood_request.receiver_id
    is_admin = getattr(actor, "role", "") == "admin"
    if not (is_owner or is_admin):
        raise DomainError("You do not have permission to complete this request.", 403)
    if blood_request.status != REQUEST_ACCEPTED:
        raise DomainError("Only accepted requests can be marked as completed.", 409)

    blood_request.status = REQUEST_COMPLETED
    blood_request.completed_at = utcnow()

    donor = blood_request.donor.donor_profile
    if donor:
        donor.total_donations = (donor.total_donations or 0) + 1
        donor.last_donation_date = date.today()

    notify(
        blood_request.donor,
        "Donation completed — thank you",
        f"Request {blood_request.reference} was marked complete. Your updated donation count is "
        f"{donor.total_donations if donor else 1}. You are a lifesaver.",
        category="request",
        link=_relative(url_for("donor.request_detail", request_id=blood_request.id)),
    )
    if is_admin and not is_owner:
        notify(
            blood_request.receiver,
            "Your request was marked complete",
            f"Request {blood_request.reference} has been marked as completed.",
            category="request",
            link=_relative(url_for("receiver.request_detail", request_id=blood_request.id)),
        )
    db.session.commit()
    return blood_request


def expire_overdue_requests() -> int:
    """Mark pending requests whose needed-by date has passed as expired."""
    stale = db.session.scalars(
        select(BloodRequest).where(
            BloodRequest.status == REQUEST_PENDING,
            BloodRequest.needed_by.is_not(None),
            BloodRequest.needed_by < date.today(),
        )
    ).all()
    for request_obj in stale:
        request_obj.status = "expired"
        notify(
            request_obj.receiver,
            "A blood request expired",
            f"Request {request_obj.reference} passed its needed-by date without a response. "
            "Search for another available donor.",
            category="request",
            link=_relative(url_for("receiver.request_detail", request_id=request_obj.id)),
        )
        notify(
            request_obj.donor,
            "A blood request expired",
            f"Request {request_obj.reference} expired before a response was recorded.",
            category="request",
            link=_relative(url_for("donor.request_detail", request_id=request_obj.id)),
        )
    if stale:
        db.session.commit()
    return len(stale)
