"""Administrator console: verification, accounts, reports and API."""
from __future__ import annotations

from conftest import login
from extensions import db
from models import DonorProfile, Report, User


def test_admin_dashboard_and_navigation(client, make_admin, make_donor):
    admin = make_admin(email="admin@example.com")
    make_donor(email="pending@example.com", is_verified=False)
    login(client, admin.email, admin=True)

    for path in (
        "/admin/",
        "/admin/donors",
        "/admin/receivers",
        "/admin/users",
        "/admin/requests",
        "/admin/reports",
    ):
        response = client.get(path)
        assert response.status_code == 200, path


def test_admin_verifies_and_unverifies_donor(client, make_admin, make_donor):
    admin = make_admin(email="admin3@example.com")
    donor = make_donor(email="verify@example.com", is_verified=False)
    login(client, admin.email, admin=True)

    response = client.post(
        f"/admin/donors/{donor.donor_profile.id}/verify",
        data={"action": "verify"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    profile = db.session.get(DonorProfile, donor.donor_profile.id)
    assert profile.is_verified is True
    assert profile.verified_by_id == admin.id
    assert profile.verified_at is not None

    client.post(
        f"/admin/donors/{donor.donor_profile.id}/verify",
        data={"action": "unverify"},
        follow_redirects=True,
    )
    profile = db.session.get(DonorProfile, donor.donor_profile.id)
    assert profile.is_verified is False
    assert profile.verified_by_id is None


def test_admin_can_disable_and_reactivate_account(client, make_admin, make_receiver):
    admin = make_admin(email="admin4@example.com")
    receiver = make_receiver(email="toggle@example.com")
    login(client, admin.email, admin=True)

    client.post(
        f"/admin/users/{receiver.id}/toggle-active", follow_redirects=True
    )
    assert db.session.get(User, receiver.id).is_active is False

    client.post(
        f"/admin/users/{receiver.id}/toggle-active", follow_redirects=True
    )
    assert db.session.get(User, receiver.id).is_active is True


def test_admin_cannot_disable_self(client, make_admin):
    admin = make_admin(email="admin5@example.com")
    login(client, admin.email, admin=True)

    response = client.post(
        f"/admin/users/{admin.id}/toggle-active", follow_redirects=True
    )
    assert b"cannot disable your own" in response.data
    assert db.session.get(User, admin.id).is_active is True


def test_non_super_admin_cannot_disable_another_admin(
    client, make_admin
):
    admin = make_admin(email="admin6@example.com", super_admin=False)
    other = make_admin(email="admin7@example.com")
    login(client, admin.email, admin=True)

    response = client.post(
        f"/admin/users/{other.id}/toggle-active", follow_redirects=True
    )
    assert b"super administrator" in response.data.lower()
    assert db.session.get(User, other.id).is_active is True


def test_admin_resolves_report(client, make_admin, make_receiver, make_donor, make_report):
    admin = make_admin(email="admin8@example.com")
    reporter = make_receiver(email="reporter@example.com")
    reported = make_donor(email="reported@example.com")
    report = make_report(reporter, reported)
    login(client, admin.email, admin=True)

    response = client.get(f"/admin/reports/{report.id}")
    assert response.status_code == 200

    response = client.post(
        f"/admin/reports/{report.id}/resolve",
        data={
            "status": "resolved",
            "admin_note": "Reviewed the profile and contacted both parties.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed = db.session.get(Report, report.id)
    assert refreshed.status == "resolved"
    assert refreshed.resolved_by_id == admin.id
    assert refreshed.resolved_at is not None
    assert "Reviewed" in refreshed.admin_note


def test_admin_review_report(client, make_admin, make_receiver, make_donor, make_report):
    admin = make_admin(email="admin9@example.com")
    reporter = make_receiver(email="reporter2@example.com")
    reported = make_donor(email="reported2@example.com")
    report = make_report(reporter, reported)
    login(client, admin.email, admin=True)

    client.post(f"/admin/reports/{report.id}/review", follow_redirects=True)
    assert db.session.get(Report, report.id).status == "reviewing"


def test_admin_stats_api(client, make_admin, make_donor):
    admin = make_admin(email="admin10@example.com")
    make_donor(email="statsdonor@example.com")
    login(client, admin.email, admin=True)

    response = client.get("/api/v1/admin/stats")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["donors"] == 1
    assert "recent_requests" not in payload["data"]


def test_admin_stats_api_forbidden_for_donor(client, make_donor):
    donor = make_donor(email="statsdonor2@example.com")
    login(client, donor.email)

    response = client.get("/api/v1/admin/stats")
    assert response.status_code == 403
    assert response.get_json()["ok"] is False
