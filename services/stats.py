"""Aggregate statistics for landing pages and dashboards."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from extensions import db
from models import BloodRequest, DonorProfile, ReceiverProfile, Report, User
from utils.constants import ACTIVE_REQUEST_STATUSES, BLOOD_GROUPS, REQUEST_STATUSES


def _count(model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int(db.session.scalar(stmt) or 0)


def public_stats() -> dict:
    donors = _count(
        DonorProfile, DonorProfile.user_id.in_(select(User.id).where(User.is_active.is_(True)))
    )
    available = _count(
        DonorProfile,
        DonorProfile.is_available.is_(True),
        DonorProfile.is_verified.is_(True),
        DonorProfile.user_id.in_(select(User.id).where(User.is_active.is_(True))),
    )
    completed = _count(BloodRequest, BloodRequest.status == "completed")
    cities = int(
        db.session.scalar(
            select(func.count(func.distinct(DonorProfile.city))).where(
                DonorProfile.user_id.in_(select(User.id).where(User.is_active.is_(True)))
            )
        )
        or 0
    )
    units = int(
        db.session.scalar(
            select(func.coalesce(func.sum(BloodRequest.units), 0)).where(
                BloodRequest.status == "completed"
            )
        )
        or 0
    )
    return {
        "donors": donors,
        "available_donors": available,
        "lives_impacted": units,
        "completed_requests": completed,
        "cities": cities,
    }


def admin_stats() -> dict:
    today = date.today()
    month_start = today.replace(day=1)
    last_30 = today - timedelta(days=30)

    total_users = _count(User)
    donors = _count(User, User.role == "donor")
    receivers = _count(User, User.role == "receiver")
    admins = _count(User, User.role == "admin")
    active_users = _count(User, User.is_active.is_(True))
    new_users_30 = _count(User, User.created_at >= last_30)
    verified_donors = _count(DonorProfile, DonorProfile.is_verified.is_(True))
    pending_verifications = _count(
        DonorProfile,
        DonorProfile.is_verified.is_(False),
        DonorProfile.user_id.in_(select(User.id).where(User.is_active.is_(True))),
    )
    available_donors = _count(
        DonorProfile,
        DonorProfile.is_available.is_(True),
        DonorProfile.is_verified.is_(True),
    )

    status_counts = {status: 0 for status in REQUEST_STATUSES}
    rows = db.session.execute(
        select(BloodRequest.status, func.count(BloodRequest.id)).group_by(BloodRequest.status)
    ).all()
    for status, total in rows:
        status_counts[status] = total

    total_requests = sum(status_counts.values())
    completed = status_counts.get("completed", 0)
    fulfilment_rate = round(completed / total_requests * 100) if total_requests else 0
    units_collected = int(
        db.session.scalar(
            select(func.coalesce(func.sum(BloodRequest.units), 0)).where(
                BloodRequest.status == "completed"
            )
        )
        or 0
    )

    blood_group_counts = {group: 0 for group in BLOOD_GROUPS}
    rows = db.session.execute(
        select(DonorProfile.blood_group, func.count(DonorProfile.id)).group_by(
            DonorProfile.blood_group
        )
    ).all()
    for group, total in rows:
        blood_group_counts[group] = total

    # Monthly signups (last 6 months) — grouped in Python for SQLite/Postgres parity.
    start_month = (today.replace(day=1) - timedelta(days=160)).replace(day=1)
    labels: list[str] = []
    buckets: dict[str, int] = {}
    cursor = start_month
    for _ in range(6):
        key = cursor.strftime("%Y-%m")
        labels.append(cursor.strftime("%b"))
        buckets[key] = 0
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    signup_rows = db.session.scalars(
        select(User.created_at).where(User.created_at >= start_month)
    ).all()
    for created_at in signup_rows:
        key = created_at.strftime("%Y-%m")
        if key in buckets:
            buckets[key] += 1

    city_rows = db.session.execute(
        select(DonorProfile.city, func.count(DonorProfile.id).label("total"))
        .group_by(DonorProfile.city)
        .order_by(func.count(DonorProfile.id).desc())
        .limit(5)
    ).all()

    open_reports = _count(Report, Report.status.in_(("open", "reviewing")))
    active_requests = _count(
        BloodRequest,
        BloodRequest.status.in_(ACTIVE_REQUEST_STATUSES),
    )

    recent_requests = db.session.scalars(
        select(BloodRequest).order_by(BloodRequest.created_at.desc()).limit(8)
    ).all()
    pending_donors = db.session.scalars(
        select(DonorProfile)
        .join(User, User.id == DonorProfile.user_id)
        .where(DonorProfile.is_verified.is_(False), User.is_active.is_(True))
        .order_by(DonorProfile.created_at.asc())
        .limit(6)
    ).all()

    return {
        "total_users": total_users,
        "donors": donors,
        "receivers": receivers,
        "admins": admins,
        "active_users": active_users,
        "new_users_30": new_users_30,
        "verified_donors": verified_donors,
        "pending_verifications": pending_verifications,
        "available_donors": available_donors,
        "total_requests": total_requests,
        "active_requests": active_requests,
        "completed_requests": completed,
        "fulfilment_rate": fulfilment_rate,
        "units_collected": units_collected,
        "new_users_this_month": _count(User, User.created_at >= month_start),
        "status_counts": status_counts,
        "blood_group_counts": blood_group_counts,
        "monthly_labels": labels,
        "monthly_values": [buckets[key] for key in buckets.keys()],
        "top_cities": [{"city": city, "total": total} for city, total in city_rows],
        "open_reports": open_reports,
        "recent_requests": recent_requests,
        "pending_donors": pending_donors,
    }


def receiver_stats(user) -> dict:
    requests = BloodRequest.query.filter_by(receiver_id=user.id)
    return {
        "total": requests.count(),
        "pending": requests.filter_by(status="pending").count(),
        "accepted": requests.filter_by(status="accepted").count(),
        "completed": requests.filter_by(status="completed").count(),
        "active": requests.filter(BloodRequest.status.in_(ACTIVE_REQUEST_STATUSES)).count(),
    }


def donor_stats(user) -> dict:
    requests = BloodRequest.query.filter_by(donor_id=user.id)
    return {
        "total": requests.count(),
        "pending": requests.filter_by(status="pending").count(),
        "accepted": requests.filter_by(status="accepted").count(),
        "completed": requests.filter_by(status="completed").count(),
        "declined": requests.filter_by(status="rejected").count(),
    }
