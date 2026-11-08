"""Optional demo data — never used automatically by the application.

Run with:
    flask --app run.py seed-demo
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta

from sqlalchemy import select

from extensions import db
from models import AdminProfile, BloodRequest, DonorProfile, Notification, ReceiverProfile, User
from services.notifications import notify

DEMO_PASSWORD = "DemoPass123"
# ``.local`` is rejected by email_validator as a special-use domain, so demo
# accounts use the documentation domain (allowed by the validator).
DEMO_DOMAIN = "example.com"


def _user(full_name: str, email: str, phone: str, role: str) -> User:
    user = User(
        full_name=full_name,
        email=email,
        phone=phone,
        role=role,
        is_active=True,
    )
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    return user


def seed_demo_data() -> dict:
    existing = User.query.filter(User.email.like(f"demo.%@{DEMO_DOMAIN}")).count()
    if existing:
        return {"donors": 0, "receivers": 0, "requests": 0, "password": DEMO_PASSWORD, "skipped": True}

    donors_spec = [
        ("Amina Bello", "A+", "Lagos", "Ikeja", 34, 64, 4, 6),
        ("Chinedu Okafor", "O-", "Enugu", "Independence Layout", 41, 78, 2, 9),
        ("Fatima Yusuf", "B+", "Abuja", "Wuse 2", 29, 58, 0, 3),
        ("Tunde Adeyemi", "O+", "Lagos", "Yaba", 37, 82, 6, 7),
        ("Ngozi Eze", "AB+", "Port Harcourt", "GRA Phase 2", 32, 61, 1, 4),
        ("Ibrahim Musa", "A-", "Kano", "Nassarawa", 45, 74, 9, 5),
        ("Blessing Etim", "B-", "Uyo", "Ewet Housing", 26, 55, 0, 2),
        ("Samuel Johnson", "O+", "Abuja", "Garki", 30, 70, 3, 8),
        ("Zainab Lawal", "AB-", "Kaduna", "Barnawa", 38, 66, 5, 3),
        ("Emeka Nwosu", "A+", "Onitsha", "Awka Road", 28, 60, 1, 4),
        ("Halima Sani", "B+", "Kano", "Tarauni", 35, 63, 7, 6),
        ("David Okon", "O-", "Calabar", "Marian", 39, 77, 2, 5),
    ]
    donors: list[User] = []
    for index, (name, group, city, area, age, weight, donations, months_ago) in enumerate(donors_spec):
        user = _user(
            name,
            f"demo.donor{index + 1}@{DEMO_DOMAIN}",
            f"+234803000{index + 10:04d}",
            "donor",
        )
        last_donation = date.today() - timedelta(days=months_ago * 30 + 20)
        profile = DonorProfile(
            blood_group=group,
            date_of_birth=date.today().replace(year=date.today().year - age),
            gender="Female" if index % 2 == 0 else "Male",
            weight_kg=weight,
            city=city,
            address=area,
            last_donation_date=last_donation,
            is_available=True,
            is_verified=index not in (6, 10),
            share_contact=True,
            total_donations=donations,
            bio="Available for emergency donations. Please share hospital details when you send a request.",
        )
        user.donor_profile = profile
        donors.append(user)

    receivers_spec = [
        ("Grace Umeh", "Lagos", "Lekki", "Lagos University Teaching Hospital", "Sibling"),
        ("Ahmed Bello", "Abuja", "Maitama", "National Hospital Abuja", "Parent"),
        ("Ruth Danjuma", "Kaduna", "Malali", "Barau Dikko Teaching Hospital", "Self"),
    ]
    receivers: list[User] = []
    for index, (name, city, area, hospital, relation) in enumerate(receivers_spec):
        user = _user(
            name,
            f"demo.receiver{index + 1}@{DEMO_DOMAIN}",
            f"+234813000{index + 10:04d}",
            "receiver",
        )
        user.receiver_profile = ReceiverProfile(
            city=city,
            address=area,
            preferred_hospital=hospital,
            patient_relation=relation,
        )
        receivers.append(user)

    db.session.flush()

    # A spread of realistic request states.
    request_specs = [
        (receivers[0], donors[1], 2, "critical", "completed", 12, "Lagos University Teaching Hospital", "Lagos"),
        (receivers[1], donors[0], 1, "urgent", "accepted", 2, "National Hospital Abuja", "Abuja"),
        (receivers[2], donors[3], 2, "urgent", "pending", 1, "Barau Dikko Teaching Hospital", "Kaduna"),
        (receivers[0], donors[7], 1, "routine", "pending", 3, "Reddington Hospital", "Lagos"),
        (receivers[1], donors[2], 2, "urgent", "rejected", 4, "Garki Hospital", "Abuja"),
        (receivers[2], donors[8], 1, "critical", "cancelled", 8, "St Gerard's Catholic Hospital", "Kaduna"),
    ]
    for receiver, donor, units, urgency, status, days_ago, hospital, city in request_specs:
        created = date.today() - timedelta(days=days_ago)
        blood_request = BloodRequest(
            reference=f"BC-DEMO-{secrets.token_hex(2).upper()}",
            receiver_id=receiver.id,
            donor_id=donor.id,
            blood_group=donor.donor_profile.blood_group,
            units=units,
            urgency=urgency,
            hospital_name=hospital,
            hospital_address=f"{city} city centre",
            city=city,
            needed_by=date.today() + timedelta(days=2),
            contact_phone=receiver.phone,
            message="Patient is admitted and the hospital blood bank is low. Please call before coming.",
            status=status,
            created_at=created,
        )
        if status in ("accepted", "completed", "rejected"):
            blood_request.responded_at = created + timedelta(hours=6)
            blood_request.donor_response = (
                "I can donate. See you at the hospital."
                if status in ("accepted", "completed")
                else "I am out of town this week, sorry."
            )
        if status == "completed":
            blood_request.completed_at = created + timedelta(days=1)
            donor.donor_profile.total_donations += 1
        if status == "cancelled":
            blood_request.cancelled_at = created + timedelta(hours=3)
        db.session.add(blood_request)
        db.session.flush()
        notify(
            donor,
            "New blood request received",
            f"{receiver.full_name} needs {units} unit(s) of {blood_request.blood_group} blood at {hospital}.",
            category="request",
            link=f"/donor/requests/{blood_request.id}",
        )

    db.session.commit()
    return {
        "donors": len(donors),
        "receivers": len(receivers),
        "requests": len(request_specs),
        "password": DEMO_PASSWORD,
        "skipped": False,
    }
