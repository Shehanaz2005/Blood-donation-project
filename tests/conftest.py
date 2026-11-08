"""Shared pytest fixtures for the Blood Connect test suite."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app import create_app
from extensions import db
from models import AdminProfile, BloodRequest, DonorProfile, ReceiverProfile, Report, User

PASSWORD = "TestPass123"


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()

        # Tests keep one app context alive for convenient DB access. Flask-Login
        # caches the resolved user on ``g``, which is app-context scoped, so
        # clear it at the start of every request to emulate real request-scoped
        # contexts (important when a test uses more than one client/session).
        from flask import g

        @application.before_request
        def _reset_login_cache():
            g.pop("_login_user", None)

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    counter = {"value": 0}

    def factory(role="donor", email=None, password=PASSWORD, **kwargs):
        counter["value"] += 1
        index = counter["value"]
        user = User(
            full_name=kwargs.pop("full_name", f"Test {role.title()} {index}"),
            email=email or f"{role}{index}@example.com",
            phone=kwargs.pop("phone", f"+234800000{index:04d}"),
            role=role,
            is_active=kwargs.pop("is_active", True),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        return user

    return factory


@pytest.fixture()
def make_donor(app, make_user):
    def factory(
        email=None,
        blood_group="A+",
        city="Lagos",
        is_verified=True,
        is_available=True,
        share_contact=True,
        age=30,
        weight=70,
        last_donation_date=None,
        **kwargs
    ):
        user = make_user(role="donor", email=email, **kwargs)
        profile = DonorProfile(
            blood_group=blood_group,
            date_of_birth=date.today().replace(year=date.today().year - age),
            gender="Female",
            weight_kg=weight,
            city=city,
            address="12 Test Street",
            last_donation_date=last_donation_date,
            is_available=is_available,
            is_verified=is_verified,
            share_contact=share_contact,
            total_donations=kwargs.get("total_donations", 0),
        )
        user.donor_profile = profile
        db.session.add(user)
        db.session.commit()
        return user

    return factory


@pytest.fixture()
def make_receiver(app, make_user):
    def factory(email=None, city="Lagos", **kwargs):
        user = make_user(role="receiver", email=email, **kwargs)
        user.receiver_profile = ReceiverProfile(
            city=city,
            address="5 Receiver Road",
            preferred_hospital="General Hospital",
            patient_relation="Self",
        )
        db.session.add(user)
        db.session.commit()
        return user

    return factory


@pytest.fixture()
def make_admin(app, make_user):
    def factory(email=None, super_admin=True, **kwargs):
        user = make_user(role="admin", email=email, **kwargs)
        user.admin_profile = AdminProfile(
            title="Test Administrator", can_manage_admins=super_admin
        )
        db.session.add(user)
        db.session.commit()
        return user

    return factory


@pytest.fixture()
def make_request(app):
    def factory(receiver, donor, status="pending", **kwargs):
        request = BloodRequest(
            reference=kwargs.pop("reference", f"BC-TEST-{BloodRequest.query.count() + 1:04d}"),
            receiver_id=receiver.id,
            donor_id=donor.id,
            blood_group=kwargs.pop("blood_group", donor.donor_profile.blood_group),
            units=kwargs.pop("units", 2),
            urgency=kwargs.pop("urgency", "urgent"),
            hospital_name=kwargs.pop("hospital_name", "General Hospital"),
            hospital_address=kwargs.pop("hospital_address", "1 Hospital Way"),
            city=kwargs.pop("city", "Lagos"),
            needed_by=kwargs.pop("needed_by", date.today() + timedelta(days=2)),
            contact_phone=kwargs.pop("contact_phone", receiver.phone),
            message=kwargs.pop("message", "Please help if you can."),
            status=status,
            **kwargs
        )
        db.session.add(request)
        db.session.commit()
        return request

    return factory


@pytest.fixture()
def make_report(app):
    def factory(reporter, reported, **kwargs):
        report = Report(
            reporter_id=reporter.id,
            reported_user_id=reported.id,
            reason=kwargs.pop("reason", "Fake or misleading profile"),
            description=kwargs.pop(
                "description", "This profile appears to contain misleading information."
            ),
            **kwargs
        )
        db.session.add(report)
        db.session.commit()
        return report

    return factory


def login(client, email, password=PASSWORD, admin=False):
    url = "/auth/admin/login" if admin else "/auth/login"
    return client.post(
        url,
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def register_donor(client, email="newdonor@example.com", **overrides):
    data = {
        "full_name": "New Donor",
        "email": email,
        "phone": "+2348012345678",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "blood_group": "O+",
        "date_of_birth": "1995-05-05",
        "gender": "Female",
        "weight_kg": "68.5",
        "city": "Lagos",
        "address": "22 Example Avenue",
        "last_donation_date": "",
        "share_contact": "y",
        "terms": "y",
    }
    data.update(overrides)
    return client.post("/auth/register/donor", data=data, follow_redirects=True)


def register_receiver(client, email="newreceiver@example.com", **overrides):
    data = {
        "full_name": "New Receiver",
        "email": email,
        "phone": "+2348098765432",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "city": "Abuja",
        "address": "9 Receiver Close",
        "patient_relation": "Self",
        "terms": "y",
    }
    data.update(overrides)
    return client.post("/auth/register/receiver", data=data, follow_redirects=True)


def request_payload(**overrides):
    data = {
        "units": "2",
        "urgency": "urgent",
        "hospital_name": "General Hospital",
        "hospital_address": "1 Hospital Way",
        "city": "Lagos",
        "needed_by": (date.today() + timedelta(days=2)).isoformat(),
        "contact_phone": "+2348011112222",
        "message": "Patient is admitted in ward 4.",
        "confirm_info": "y",
    }
    data.update(overrides)
    return data
