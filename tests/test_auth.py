"""Registration, login, logout and role protection."""
from __future__ import annotations

from conftest import login, register_donor, register_receiver
from extensions import db
from models import DonorProfile, ReceiverProfile, User


def test_donor_registration_creates_profile_and_logs_in(client, app):
    response = register_donor(client)
    assert response.status_code == 200
    assert b"Donor dashboard" in response.data or b"pending administrator verification" in response.data

    with app.app_context():
        user = User.query.filter_by(email="newdonor@example.com").first()
        assert user is not None
        assert user.role == "donor"
        assert user.donor_profile is not None
        assert user.donor_profile.blood_group == "O+"
        assert user.donor_profile.city == "Lagos"
        assert user.donor_profile.is_verified is False
        assert user.check_password("TestPass123")


def test_donor_registration_rejects_duplicate_email(client, make_donor):
    make_donor(email="taken@example.com")
    response = register_donor(client, email="taken@example.com")
    assert response.status_code == 200
    assert b"already exists" in response.data


def test_donor_registration_rejects_underage(client):
    response = register_donor(client, date_of_birth="2015-01-01")
    assert b"at least 18" in response.data


def test_receiver_registration(client, app):
    response = register_receiver(client)
    assert response.status_code == 200
    assert b"receiver account" in response.data.lower()

    with app.app_context():
        user = User.query.filter_by(email="newreceiver@example.com").first()
        assert user is not None
        assert user.role == "receiver"
        assert user.receiver_profile is not None
        assert user.receiver_profile.city == "Abuja"


def test_login_and_logout(client, make_receiver):
    receiver = make_receiver(email="login@example.com")
    response = login(client, receiver.email)
    assert response.status_code == 200
    assert b"Welcome back" in response.data

    response = client.post("/auth/logout", follow_redirects=True)
    assert response.status_code == 200
    assert b"been signed out" in response.data


def test_login_rejects_wrong_password(client, make_receiver):
    receiver = make_receiver(email="wrong@example.com")
    response = login(client, receiver.email, password="WrongPass123")
    assert b"Invalid email or password" in response.data


def test_disabled_account_cannot_login(client, make_donor):
    donor = make_donor(email="disabled@example.com", is_active=False)
    response = login(client, donor.email)
    assert b"disabled" in response.data.lower()


def test_admin_login_requires_admin_role(client, make_receiver, make_admin):
    receiver = make_receiver(email="notadmin@example.com")
    response = login(client, receiver.email, admin=True)
    assert b"Administrator credentials are required" in response.data

    admin = make_admin(email="admin@example.com")
    response = login(client, admin.email, admin=True)
    assert response.status_code == 200
    assert b"Platform overview" in response.data


def test_anonymous_dashboard_redirects_to_login(client):
    response = client.get("/donor/dashboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_donor_cannot_open_receiver_dashboard(client, make_donor):
    donor = make_donor(email="rolecheck@example.com")
    login(client, donor.email)
    response = client.get("/receiver/dashboard")
    assert response.status_code == 403


def test_receiver_cannot_open_admin_console(client, make_receiver):
    receiver = make_receiver(email="rolecheck2@example.com")
    login(client, receiver.email)
    response = client.get("/admin/")
    assert response.status_code == 403


def test_donor_dashboard_loads(client, make_donor):
    donor = make_donor(email="dash@example.com")
    login(client, donor.email)
    response = client.get("/donor/dashboard")
    assert response.status_code == 200
    assert b"availabilitySwitch" in response.data


def test_receiver_dashboard_loads(client, make_receiver):
    receiver = make_receiver(email="rdash@example.com")
    login(client, receiver.email)
    response = client.get("/receiver/dashboard")
    assert response.status_code == 200
    assert b"Find donors" in response.data


def test_admin_dashboard_loads(client, make_admin):
    admin = make_admin(email="admin2@example.com")
    login(client, admin.email, admin=True)
    response = client.get("/admin/")
    assert response.status_code == 200
    assert b"growthChart" in response.data
