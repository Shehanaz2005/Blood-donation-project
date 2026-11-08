"""Administrator console: moderation, verification and platform oversight."""
from __future__ import annotations

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
from sqlalchemy import case, func, or_, select

from extensions import db
from forms.receiver import AdminReportForm
from models import BloodRequest, DonorProfile, ReceiverProfile, Report, User
from services.requests import (
    DomainError,
    cancel_request,
    complete_request,
    expire_overdue_requests,
)
from services.notifications import notify
from services.stats import admin_stats
from utils.constants import BLOOD_GROUPS, REQUEST_STATUSES, REPORT_STATUSES, REPORT_STATUS_META
from utils.helpers import role_required, utcnow

admin_bp = Blueprint("admin", __name__)


def _touch_admin():
    profile = current_user.admin_profile
    if profile:
        profile.last_action_at = utcnow()


def _active_admin_count(exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return int(db.session.scalar(stmt) or 0)


@admin_bp.get("/")
@login_required
@role_required("admin")
def dashboard():
    expire_overdue_requests()
    stats = admin_stats()
    chart_data = {
        "bloodGroups": {
            "labels": list(stats["blood_group_counts"].keys()),
            "values": list(stats["blood_group_counts"].values()),
        },
        "statuses": {
            "labels": [status.title() for status in stats["status_counts"].keys()],
            "values": list(stats["status_counts"].values()),
        },
        "monthly": {
            "labels": stats["monthly_labels"],
            "values": stats["monthly_values"],
        },
    }
    return render_template("admin/dashboard.html", stats=stats, chart_data=chart_data)


# ----------------------------------------------------------------------
# Donors
# ----------------------------------------------------------------------
@admin_bp.get("/donors")
@login_required
@role_required("admin")
def donors():
    q = (request.args.get("q") or "").strip()
    blood_group = (request.args.get("blood_group") or "").strip().upper()
    if blood_group not in BLOOD_GROUPS:
        blood_group = ""
    verified = (request.args.get("verified") or "all").strip()
    if verified not in {"all", "1", "0"}:
        verified = "all"
    availability = (request.args.get("availability") or "all").strip()
    if availability not in {"all", "1", "0"}:
        availability = "all"
    page = max(request.args.get("page", 1, type=int), 1)

    stmt = select(DonorProfile).join(User, User.id == DonorProfile.user_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
                DonorProfile.city.ilike(like),
            )
        )
    if blood_group:
        stmt = stmt.where(DonorProfile.blood_group == blood_group)
    if verified != "all":
        stmt = stmt.where(DonorProfile.is_verified.is_(verified == "1"))
    if availability != "all":
        stmt = stmt.where(DonorProfile.is_available.is_(availability == "1"))
    stmt = stmt.order_by(DonorProfile.is_verified.asc(), DonorProfile.created_at.desc())
    pagination = db.paginate(stmt, page=page, per_page=15, error_out=False)

    return render_template(
        "admin/donors.html",
        pagination=pagination,
        q=q,
        blood_group=blood_group,
        verified=verified,
        availability=availability,
    )


@admin_bp.post("/donors/<int:donor_id>/verify")
@login_required
@role_required("admin")
def verify_donor(donor_id: int):
    donor = db.session.get(DonorProfile, donor_id)
    if not donor:
        abort(404)
    action = (request.form.get("action") or "verify").strip().lower()
    if action == "unverify":
        if donor.is_verified:
            donor.unverify()
            notify(
                donor.user,
                "Donor verification removed",
                "An administrator has removed your verified badge after a review. "
                "You can no longer accept new requests until your profile is verified again.",
                category="verification",
                link=url_for("donor.profile_edit"),
            )
            flash(f"{donor.user.full_name} is no longer verified.", "warning")
    else:
        if not donor.is_verified:
            donor.verify(current_user)
            notify(
                donor.user,
                "Your donor profile is verified",
                "You are now a verified donor. Receivers can send you blood requests — keep your "
                "availability up to date.",
                category="verification",
                link=url_for("donor.dashboard"),
            )
            flash(f"{donor.user.full_name} has been verified.", "success")
    _touch_admin()
    db.session.commit()
    return redirect(request.referrer or url_for("admin.donors"))


# ----------------------------------------------------------------------
# Receivers
# ----------------------------------------------------------------------
@admin_bp.get("/receivers")
@login_required
@role_required("admin")
def receivers():
    q = (request.args.get("q") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    stmt = select(ReceiverProfile).join(User, User.id == ReceiverProfile.user_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
                ReceiverProfile.city.ilike(like),
            )
        )
    stmt = stmt.order_by(User.created_at.desc())
    pagination = db.paginate(stmt, page=page, per_page=15, error_out=False)
    return render_template("admin/receivers.html", pagination=pagination, q=q)


# ----------------------------------------------------------------------
# All users / account status
# ----------------------------------------------------------------------
@admin_bp.get("/users")
@login_required
@role_required("admin")
def users():
    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "all").strip()
    if role not in {"all", "donor", "receiver", "admin"}:
        role = "all"
    status = (request.args.get("status") or "all").strip()
    if status not in {"all", "active", "disabled"}:
        status = "all"
    page = max(request.args.get("page", 1, type=int), 1)

    stmt = select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(User.full_name.ilike(like), User.email.ilike(like), User.phone.ilike(like))
        )
    if role != "all":
        stmt = stmt.where(User.role == role)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "disabled":
        stmt = stmt.where(User.is_active.is_(False))
    stmt = stmt.order_by(User.created_at.desc())
    pagination = db.paginate(stmt, page=page, per_page=15, error_out=False)
    return render_template(
        "admin/users.html",
        pagination=pagination,
        q=q,
        role=role,
        status=status,
    )


@admin_bp.post("/users/<int:user_id>/toggle-active")
@login_required
@role_required("admin")
def toggle_active(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash("You cannot disable your own administrator account.", "danger")
        return redirect(request.referrer or url_for("admin.users"))
    if user.role == "admin":
        super_admin = bool(current_user.admin_profile and current_user.admin_profile.can_manage_admins)
        if not super_admin:
            flash("Only a super administrator can change another administrator's status.", "danger")
            return redirect(request.referrer or url_for("admin.users"))
        if user.is_active and _active_admin_count(exclude_id=user.id) == 0:
            flash("At least one active administrator must remain.", "danger")
            return redirect(request.referrer or url_for("admin.users"))

    user.is_active = not user.is_active
    _touch_admin()
    if user.is_active:
        notify(
            user,
            "Your account has been reactivated",
            "An administrator restored access to your account. You can sign in again.",
            category="account",
        )
        flash(f"{user.full_name}'s account has been reactivated.", "success")
    else:
        notify(
            user,
            "Your account has been disabled",
            "An administrator disabled your account after a review. Contact support if you need help.",
            category="account",
        )
        flash(f"{user.full_name}'s account has been disabled.", "warning")
    db.session.commit()
    return redirect(request.referrer or url_for("admin.users"))


# ----------------------------------------------------------------------
# Blood requests
# ----------------------------------------------------------------------
@admin_bp.get("/requests")
@login_required
@role_required("admin")
def requests_list():
    expire_overdue_requests()
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "all").strip().lower()
    if status not in REQUEST_STATUSES and status != "all":
        status = "all"
    urgency = (request.args.get("urgency") or "all").strip().lower()
    if urgency not in {"routine", "urgent", "critical"}:
        urgency = "all"
    page = max(request.args.get("page", 1, type=int), 1)

    stmt = select(BloodRequest)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                BloodRequest.reference.ilike(like),
                BloodRequest.hospital_name.ilike(like),
                BloodRequest.city.ilike(like),
            )
        )
    if status != "all":
        stmt = stmt.where(BloodRequest.status == status)
    if urgency != "all":
        stmt = stmt.where(BloodRequest.urgency == urgency)
    stmt = stmt.order_by(
        case((BloodRequest.status == "pending", 0), (BloodRequest.status == "accepted", 1), else_=2),
        BloodRequest.created_at.desc(),
    )
    pagination = db.paginate(stmt, page=page, per_page=15, error_out=False)
    return render_template(
        "admin/requests.html",
        pagination=pagination,
        q=q,
        status=status,
        urgency=urgency,
    )


@admin_bp.get("/requests/<int:request_id>")
@login_required
@role_required("admin")
def request_detail(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request:
        abort(404)
    return render_template("admin/request_detail.html", blood_request=blood_request)


@admin_bp.post("/requests/<int:request_id>/status")
@login_required
@role_required("admin")
def update_request_status(request_id: int):
    blood_request = db.session.get(BloodRequest, request_id)
    if not blood_request:
        abort(404)
    action = (request.form.get("action") or "").strip().lower()
    try:
        if action == "cancel":
            cancel_request(blood_request, current_user, request.form.get("reason", ""))
            flash(f"Request {blood_request.reference} cancelled.", "info")
        elif action == "complete":
            complete_request(blood_request, current_user)
            flash(f"Request {blood_request.reference} marked complete.", "success")
        else:
            flash("Choose a valid action.", "danger")
    except DomainError as exc:
        db.session.rollback()
        flash(exc.message, "danger")
    else:
        _touch_admin()
        db.session.commit()
    return redirect(url_for("admin.request_detail", request_id=request_id))


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------
@admin_bp.get("/reports")
@login_required
@role_required("admin")
def reports():
    status = (request.args.get("status") or "open").strip().lower()
    if status not in REPORT_STATUSES and status != "all":
        status = "open"
    page = max(request.args.get("page", 1, type=int), 1)
    stmt = select(Report)
    if status != "all":
        if status == "open":
            stmt = stmt.where(Report.status.in_(("open", "reviewing")))
        else:
            stmt = stmt.where(Report.status == status)
    stmt = stmt.order_by(
        case((Report.status == "open", 0), (Report.status == "reviewing", 1), else_=2),
        Report.created_at.desc(),
    )
    pagination = db.paginate(stmt, page=page, per_page=12, error_out=False)
    return render_template(
        "admin/reports.html",
        pagination=pagination,
        status=status,
        status_meta=REPORT_STATUS_META,
    )


@admin_bp.get("/reports/<int:report_id>")
@login_required
@role_required("admin")
def report_detail(report_id: int):
    report = db.session.get(Report, report_id)
    if not report:
        abort(404)
    form = AdminReportForm(status="resolved")
    return render_template(
        "admin/report_detail.html",
        report=report,
        form=form,
        status_meta=REPORT_STATUS_META,
    )


@admin_bp.post("/reports/<int:report_id>/resolve")
@login_required
@role_required("admin")
def resolve_report(report_id: int):
    report = db.session.get(Report, report_id)
    if not report:
        abort(404)
    form = AdminReportForm()
    if not form.validate_on_submit():
        flash("Add a short internal note (at least 5 characters) before saving.", "danger")
        return redirect(url_for("admin.report_detail", report_id=report.id))

    report.status = form.status.data
    report.admin_note = form.admin_note.data.strip()
    report.resolved_by_id = current_user.id
    report.resolved_at = utcnow()
    notify(
        report.reporter,
        "Your report has been reviewed",
        f"Your report about {report.reported_user.full_name} was marked "
        f"{report.status}. Thank you for helping keep Blood Connect safe.",
        category="report",
        link=url_for("main.notifications"),
    )
    _touch_admin()
    db.session.commit()
    flash("Report saved. The reporter has been notified.", "success")
    return redirect(url_for("admin.report_detail", report_id=report.id))


@admin_bp.post("/reports/<int:report_id>/review")
@login_required
@role_required("admin")
def review_report(report_id: int):
    report = db.session.get(Report, report_id)
    if not report:
        abort(404)
    if report.status == "open":
        report.status = "reviewing"
        _touch_admin()
        db.session.commit()
        flash("Report marked as under review.", "info")
    return redirect(url_for("admin.report_detail", report_id=report.id))
