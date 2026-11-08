"""Public pages: landing, about, donor directory and profiles."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from extensions import db
from forms.receiver import ReportForm
from models import BloodRequest, DonorProfile, Notification, Report, User
from services.donors import (
    donor_cities,
    donor_count_by_group,
    parse_search_filters,
    search_donors,
    serialise_donor_card,
    serialise_donor_detail,
)
from services.notifications import mark_all_read, notify_many
from services.stats import public_stats
from utils.constants import ACTIVE_REQUEST_STATUSES
from utils.helpers import safe_next_url

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def home():
    stats = public_stats()
    group_counts = donor_count_by_group()
    featured = db.session.scalars(
        select(DonorProfile)
        .join(User, User.id == DonorProfile.user_id)
        .where(
            User.is_active.is_(True),
            DonorProfile.is_verified.is_(True),
            DonorProfile.is_available.is_(True),
        )
        .order_by(DonorProfile.total_donations.desc(), DonorProfile.updated_at.desc())
        .limit(3)
    ).all()
    featured_donors = [serialise_donor_card(donor, current_user) for donor in featured]
    return render_template(
        "public/home.html",
        stats=stats,
        group_counts=group_counts,
        featured_donors=featured_donors,
    )


@main_bp.get("/about")
def about():
    stats = public_stats()
    group_counts = donor_count_by_group()
    return render_template("public/about.html", stats=stats, group_counts=group_counts)


@main_bp.get("/find-donors")
def find_donors():
    filters = parse_search_filters(request.args)
    pagination = search_donors(filters)
    donors = [serialise_donor_card(donor, current_user) for donor in pagination.items]
    cities = donor_cities()
    return render_template(
        "public/find_donors.html",
        filters=filters,
        pagination=pagination,
        donors=donors,
        cities=cities,
        result_count=pagination.total,
    )


@main_bp.get("/donors/<int:donor_id>")
def donor_profile(donor_id: int):
    donor = db.session.get(DonorProfile, donor_id)
    if not donor or not donor.user or not donor.user.is_active:
        abort(404)

    viewer = current_user if current_user.is_authenticated else None
    data = serialise_donor_detail(donor, viewer)

    active_request = None
    if viewer and viewer.is_receiver:
        active_request = db.session.scalar(
            select(BloodRequest).where(
                BloodRequest.receiver_id == viewer.id,
                BloodRequest.donor_id == donor.user_id,
                BloodRequest.status.in_(ACTIVE_REQUEST_STATUSES),
            )
        )

    similar = db.session.scalars(
        select(DonorProfile)
        .join(User, User.id == DonorProfile.user_id)
        .where(
            User.is_active.is_(True),
            DonorProfile.id != donor.id,
            DonorProfile.blood_group == donor.blood_group,
            DonorProfile.is_available.is_(True),
        )
        .order_by(DonorProfile.total_donations.desc())
        .limit(3)
    ).all()

    return render_template(
        "public/donor_profile.html",
        donor=donor,
        data=data,
        active_request=active_request,
        similar=[serialise_donor_card(item, viewer) for item in similar],
        viewer=viewer,
    )


@main_bp.get("/notifications")
@login_required
def notifications():
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = current_user.notifications.paginate(
        page=page, per_page=15, error_out=False
    )
    return render_template("public/notifications.html", pagination=pagination)


@main_bp.post("/notifications/<int:notification_id>/read")
@login_required
def read_notification(notification_id: int):
    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != current_user.id:
        abort(404)
    notification.is_read = True
    db.session.commit()
    target = safe_next_url(notification.link) if notification.link else None
    return redirect(target or url_for("main.notifications"))


@main_bp.post("/notifications/read-all")
@login_required
def read_all_notifications():
    mark_all_read(current_user)
    flash("All notifications marked as read.", "success")
    return redirect(request.referrer if request.referrer else url_for("main.notifications"))


@main_bp.get("/healthz")
def healthz():
    try:
        db.session.execute(db.text("SELECT 1"))
        database = "up"
    except Exception:  # pragma: no cover - deployment probe
        database = "down"
    return jsonify({"ok": database == "up", "database": database}), 200 if database == "up" else 503


# ----------------------------------------------------------------------
# User reports
# ----------------------------------------------------------------------
@main_bp.route("/report/<int:user_id>", methods=["GET", "POST"])
@login_required
def report_user(user_id: int):
    target = db.session.get(User, user_id)
    if not target or not target.is_active or target.role == "admin":
        abort(404)
    if target.id == current_user.id:
        flash("You cannot report yourself.", "warning")
        return redirect(url_for("main.home"))
    if current_user.role == "admin":
        flash("Administrators review reports from the admin console.", "info")
        return redirect(url_for("admin.reports"))

    existing = db.session.scalar(
        select(Report.id).where(
            Report.reporter_id == current_user.id,
            Report.reported_user_id == target.id,
            Report.status.in_(("open", "reviewing")),
        )
    )
    form = ReportForm()
    if existing and request.method == "GET":
        flash("You already have an open report about this user. An administrator is reviewing it.", "info")

    if form.validate_on_submit():
        if existing:
            flash("You already have an open report about this user.", "warning")
            return redirect(url_for("main.report_user", user_id=target.id))
        report = Report(
            reporter_id=current_user.id,
            reported_user_id=target.id,
            reason=form.reason.data,
            description=form.description.data.strip(),
        )
        db.session.add(report)
        admins = User.query.filter_by(role="admin", is_active=True).all()
        notify_many(
            admins,
            "New user report submitted",
            f"{current_user.full_name} reported {target.full_name}: {form.reason.data}.",
            category="report",
            link=url_for("admin.reports"),
        )
        db.session.commit()
        flash("Report submitted. An administrator will review it. Thank you for helping keep the platform safe.", "success")
        return redirect(url_for("main.donor_profile", donor_id=target.donor_profile.id) if target.donor_profile else url_for("main.home"))

    return render_template(
        "public/report.html",
        form=form,
        target=target,
        existing=existing,
    )

