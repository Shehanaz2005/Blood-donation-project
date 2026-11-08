"""Donor directory search, serialisation and privacy rules."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from flask import current_app, url_for
from sqlalchemy import func, or_, select

from extensions import db
from models import BloodRequest, DonorProfile, User
from utils.constants import (
    BLOOD_GROUPS,
    REQUEST_ACCEPTED,
    REQUEST_COMPLETED,
    compatible_donor_groups,
)
from utils.helpers import is_valid_city


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bool_arg(args, name: str, default: bool) -> bool:
    """Read a checkbox-style query param.

    Forms submit a hidden ``0`` followed by ``1`` when checked, so the last
    value wins. Direct API callers can send a single value.
    """
    values = args.getlist(name) if hasattr(args, "getlist") else [args.get(name)]
    values = [value for value in values if value not in (None, "")]
    if not values:
        return default
    return _as_bool(values[-1], default)


def parse_search_filters(args) -> dict:
    blood_group = (args.get("blood_group") or "").strip().upper()
    if blood_group not in BLOOD_GROUPS:
        blood_group = ""
    city = (args.get("city") or "").strip()
    if not is_valid_city(city):
        city = ""
    sort = (args.get("sort") or "recommended").strip().lower()
    if sort not in {"recommended", "newest", "donations", "name"}:
        sort = "recommended"
    try:
        page = max(int(args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    return {
        "blood_group": blood_group,
        "city": city,
        "available": _bool_arg(args, "available", True),
        "verified": _bool_arg(args, "verified", True),
        "eligible": _bool_arg(args, "eligible", True),
        "compatible": _bool_arg(args, "compatible", False) and bool(blood_group),
        "sort": sort,
        "page": page,
    }


def search_donors(filters: dict, per_page: int | None = None):
    """Return a SQLAlchemy pagination object of active donor profiles."""
    per_page = per_page or current_app.config.get("DONORS_PER_PAGE", 9)
    per_page = min(max(int(per_page), 1), 48)

    stmt = (
        select(DonorProfile)
        .join(User, User.id == DonorProfile.user_id)
        .where(User.is_active.is_(True))
    )

    if filters.get("blood_group"):
        if filters.get("compatible"):
            groups = compatible_donor_groups(filters["blood_group"])
            stmt = stmt.where(DonorProfile.blood_group.in_(groups))
        else:
            stmt = stmt.where(DonorProfile.blood_group == filters["blood_group"])

    if filters.get("city"):
        stmt = stmt.where(DonorProfile.city.ilike(f"%{filters['city']}%"))

    if filters.get("available"):
        stmt = stmt.where(DonorProfile.is_available.is_(True))

    if filters.get("verified"):
        stmt = stmt.where(DonorProfile.is_verified.is_(True))

    if filters.get("eligible"):
        today = date.today()
        cooldown = int(current_app.config.get("DONATION_COOLDOWN_DAYS", 90))
        latest_allowed = today - timedelta(days=cooldown)

        def years_ago(years: int) -> date:
            try:
                return today.replace(year=today.year - years)
            except ValueError:  # 29 February
                return today.replace(year=today.year - years, day=28)

        max_age_cutoff = years_ago(current_app.config.get("MIN_DONOR_AGE", 18))
        min_age_cutoff = years_ago(current_app.config.get("MAX_DONOR_AGE", 65))
        stmt = stmt.where(
            or_(
                DonorProfile.last_donation_date.is_(None),
                DonorProfile.last_donation_date <= latest_allowed,
            ),
            DonorProfile.date_of_birth <= max_age_cutoff,
            DonorProfile.date_of_birth >= min_age_cutoff,
            or_(
                DonorProfile.weight_kg.is_(None),
                DonorProfile.weight_kg >= current_app.config.get("MIN_DONOR_WEIGHT_KG", 50),
            ),
        )

    if filters.get("sort") == "newest":
        stmt = stmt.order_by(DonorProfile.created_at.desc())
    elif filters.get("sort") == "donations":
        stmt = stmt.order_by(DonorProfile.total_donations.desc(), DonorProfile.updated_at.desc())
    elif filters.get("sort") == "name":
        stmt = stmt.order_by(User.full_name.asc())
    else:
        stmt = stmt.order_by(
            DonorProfile.is_verified.desc(),
            DonorProfile.total_donations.desc(),
            DonorProfile.updated_at.desc(),
        )

    return db.paginate(stmt, page=filters.get("page", 1), per_page=per_page, error_out=False)


def _name_for(donor: DonorProfile) -> str:
    return donor.user.full_name if donor.user else "Donor"


def serialise_donor_card(donor: DonorProfile, viewer=None) -> dict:
    """Public card data — contact details never appear here."""
    profile = donor
    user = donor.user
    can_request = bool(
        viewer
        and getattr(viewer, "is_authenticated", False)
        and viewer.is_receiver
        and profile.can_accept_requests
        and user.id != viewer.id
    )
    return {
        "id": profile.id,
        "user_id": user.id,
        "name": _name_for(profile),
        "initials": user.initials if user else "D",
        "blood_group": profile.blood_group,
        "city": profile.city,
        "is_available": profile.is_available,
        "is_verified": profile.is_verified,
        "is_eligible": profile.is_eligible,
        "is_in_cooldown": profile.is_in_cooldown,
        "can_accept_requests": profile.can_accept_requests,
        "total_donations": profile.total_donations or 0,
        "donor_level": profile.donation_streak_label,
        "last_donation_date": profile.last_donation_date.isoformat()
        if profile.last_donation_date
        else None,
        "next_eligible_date": profile.next_eligible_date.isoformat()
        if profile.next_eligible_date
        else None,
        "member_since": profile.created_at.strftime("%b %Y") if profile.created_at else None,
        "bio": (profile.bio or "").strip()[:160] or None,
        "url": url_for("main.donor_profile", donor_id=profile.id),
        "request_url": url_for("receiver.new_request", donor_id=profile.id) if can_request else None,
        "login_url": url_for("auth.login", next=url_for("main.donor_profile", donor_id=profile.id)),
    }


def can_view_contact(donor: DonorProfile, viewer) -> bool:
    """Contact visibility: admin, the donor, or a receiver with an accepted request.

    The donor must also have opted in via ``share_contact``.
    """
    if not viewer or not getattr(viewer, "is_authenticated", False):
        return False
    if viewer.role == "admin":
        return True
    if viewer.id == donor.user_id:
        return True
    if not donor.share_contact:
        return False
    if viewer.role != "receiver":
        return False
    accepted = db.session.scalar(
        select(func.count(BloodRequest.id)).where(
            BloodRequest.donor_id == donor.user_id,
            BloodRequest.receiver_id == viewer.id,
            BloodRequest.status.in_((REQUEST_ACCEPTED, REQUEST_COMPLETED)),
        )
    )
    return bool(accepted)


def serialise_donor_detail(donor: DonorProfile, viewer=None) -> dict:
    data = serialise_donor_card(donor, viewer)
    user = donor.user
    contact_allowed = can_view_contact(donor, viewer)
    data.update(
        {
            "age": donor.age,
            "gender": donor.gender,
            "address": donor.address if contact_allowed else None,
            "email": user.email if contact_allowed and viewer and viewer.role == "admin" else None,
            "phone": user.phone if contact_allowed else None,
            "contact_allowed": contact_allowed,
            "share_contact": donor.share_contact,
            "eligibility_reasons": donor.eligibility_reasons,
            "verified_at": donor.verified_at.isoformat() if donor.verified_at else None,
            "profile_completeness": donor.profile_completeness,
        }
    )
    return data


def donor_cities(limit: int = 60) -> list[str]:
    rows = db.session.execute(
        select(DonorProfile.city, func.count(DonorProfile.id).label("total"))
        .join(User, User.id == DonorProfile.user_id)
        .where(User.is_active.is_(True), DonorProfile.city.is_not(None))
        .group_by(DonorProfile.city)
        .order_by(func.count(DonorProfile.id).desc(), DonorProfile.city.asc())
        .limit(limit)
    ).all()
    return [row[0] for row in rows if row[0]]


def donor_count_by_group() -> dict[str, int]:
    rows = db.session.execute(
        select(DonorProfile.blood_group, func.count(DonorProfile.id))
        .join(User, User.id == DonorProfile.user_id)
        .where(User.is_active.is_(True))
        .group_by(DonorProfile.blood_group)
    ).all()
    counts = {group: 0 for group in BLOOD_GROUPS}
    for group, total in rows:
        counts[group] = total
    return counts
