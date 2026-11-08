"""Blood request lifecycle, permissions and privacy."""
from __future__ import annotations

from datetime import date, timedelta

from conftest import login, request_payload
from extensions import db
from models import BloodRequest, DonorProfile
from services.requests import expire_overdue_requests


def test_receiver_creates_request_for_verified_donor(
    client, make_receiver, make_donor
):
    receiver = make_receiver(email="requestor@example.com")
    donor = make_donor(email="requested@example.com")
    login(client, receiver.email)

    response = client.post(
        f"/receiver/requests/new/{donor.donor_profile.id}",
        data=request_payload(),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"sent to" in response.data

    blood_request = BloodRequest.query.one()
    assert blood_request.receiver_id == receiver.id
    assert blood_request.donor_id == donor.id
    assert blood_request.status == "pending"
    assert blood_request.blood_group == donor.donor_profile.blood_group


def test_receiver_cannot_request_unverified_donor(
    client, make_receiver, make_donor
):
    receiver = make_receiver(email="requestor2@example.com")
    donor = make_donor(email="unverified2@example.com", is_verified=False)
    login(client, receiver.email)

    response = client.post(
        f"/receiver/requests/new/{donor.donor_profile.id}",
        data=request_payload(),
        follow_redirects=True,
    )
    assert b"not currently accepting requests" in response.data
    assert BloodRequest.query.count() == 0


def test_donor_cannot_accept_unverified_profile(
    app, make_receiver, make_donor, make_request
):
    receiver = make_receiver(email="receiver3@example.com")
    donor = make_donor(email="donor3@example.com", is_verified=False)
    blood_request = make_request(receiver, donor, status="pending")

    donor_client = app.test_client()
    login(donor_client, donor.email)
    response = donor_client.post(
        f"/donor/requests/{blood_request.id}/respond",
        data={"action": "accept", "note": "I can help."},
        follow_redirects=True,
    )
    assert b"verified" in response.data.lower()

    refreshed = db.session.get(BloodRequest, blood_request.id)
    assert refreshed.status == "pending"


def test_accept_flow_unlocks_contact_and_completion(
    app, make_receiver, make_donor, make_request
):
    receiver = make_receiver(email="receiver4@example.com")
    donor = make_donor(
        email="donor4@example.com", share_contact=True, phone="+2348012340000"
    )
    blood_request = make_request(receiver, donor, status="pending")

    donor_client = app.test_client()
    login(donor_client, donor.email)
    response = donor_client.post(
        f"/donor/requests/{blood_request.id}/respond",
        data={"action": "accept", "note": "I will be there at 4pm."},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed = db.session.get(BloodRequest, blood_request.id)
    assert refreshed.status == "accepted"
    assert refreshed.responded_at is not None
    assert refreshed.donor_response == "I will be there at 4pm."

    receiver_client = app.test_client()
    login(receiver_client, receiver.email)
    detail = receiver_client.get(f"/receiver/requests/{blood_request.id}")
    assert detail.status_code == 200
    assert donor.phone.encode() in detail.data

    response = receiver_client.post(
        f"/receiver/requests/{blood_request.id}/complete", follow_redirects=True
    )
    assert response.status_code == 200

    completed = db.session.get(BloodRequest, blood_request.id)
    assert completed.status == "completed"
    assert completed.completed_at is not None

    profile = db.session.get(DonorProfile, donor.donor_profile.id)
    assert profile.total_donations == 1
    assert profile.last_donation_date == date.today()
    assert profile.is_in_cooldown is True
    assert profile.next_eligible_date > date.today()


def test_accept_keeps_contact_private_when_donor_opted_out(
    app, make_receiver, make_donor, make_request
):
    receiver = make_receiver(email="receiver5@example.com")
    donor = make_donor(email="donor5@example.com", share_contact=False)
    blood_request = make_request(receiver, donor, status="pending")

    donor_client = app.test_client()
    login(donor_client, donor.email)
    donor_client.post(
        f"/donor/requests/{blood_request.id}/respond",
        data={"action": "accept"},
        follow_redirects=True,
    )

    receiver_client = app.test_client()
    login(receiver_client, receiver.email)
    detail = receiver_client.get(f"/receiver/requests/{blood_request.id}")
    assert donor.phone.encode() not in detail.data
    assert b"Contact stays private" in detail.data


def test_duplicate_active_request_is_blocked(
    client, make_receiver, make_donor
):
    receiver = make_receiver(email="receiver6@example.com")
    donor = make_donor(email="donor6@example.com")
    login(client, receiver.email)

    first = client.post(
        f"/receiver/requests/new/{donor.donor_profile.id}",
        data=request_payload(),
        follow_redirects=True,
    )
    assert b"sent to" in first.data

    second = client.post(
        f"/receiver/requests/new/{donor.donor_profile.id}",
        data=request_payload(),
        follow_redirects=True,
    )
    assert b"already have an active request" in second.data
    assert BloodRequest.query.count() == 1


def test_receiver_can_cancel_pending_request(
    client, make_receiver, make_donor, make_request
):
    receiver = make_receiver(email="receiver7@example.com")
    donor = make_donor(email="donor7@example.com")
    blood_request = make_request(receiver, donor, status="pending")

    login(client, receiver.email)
    response = client.post(
        f"/receiver/requests/{blood_request.id}/cancel",
        data={"reason": "The patient was transferred."},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed = db.session.get(BloodRequest, blood_request.id)
    assert refreshed.status == "cancelled"
    assert refreshed.cancelled_at is not None


def test_donor_can_decline_request(app, make_receiver, make_donor, make_request):
    receiver = make_receiver(email="receiver8@example.com")
    donor = make_donor(email="donor8@example.com")
    blood_request = make_request(receiver, donor, status="pending")

    donor_client = app.test_client()
    login(donor_client, donor.email)
    response = donor_client.post(
        f"/donor/requests/{blood_request.id}/respond",
        data={"action": "reject", "note": "I am out of town."},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed = db.session.get(BloodRequest, blood_request.id)
    assert refreshed.status == "rejected"


def test_overdue_requests_expire(app, make_receiver, make_donor, make_request):
    receiver = make_receiver(email="receiver9@example.com")
    donor = make_donor(email="donor9@example.com")
    blood_request = make_request(
        receiver,
        donor,
        status="pending",
        needed_by=date.today() - timedelta(days=1),
    )

    count = expire_overdue_requests()
    assert count == 1

    refreshed = db.session.get(BloodRequest, blood_request.id)
    assert refreshed.status == "expired"


def test_donor_availability_toggle(client, make_donor):
    donor = make_donor(email="available@example.com", is_available=True)
    login(client, donor.email)

    response = client.post(
        "/donor/availability",
        json={"available": False},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["is_available"] is False

    profile = db.session.get(DonorProfile, donor.donor_profile.id)
    assert profile.is_available is False


def test_availability_blocked_when_in_cooldown(client, make_donor):
    donor = make_donor(
        email="cooldown2@example.com",
        is_available=False,
        last_donation_date=date.today() - timedelta(days=5),
    )
    login(client, donor.email)

    response = client.post(
        "/donor/availability",
        json={"available": True},
        headers={"Accept": "application/json"},
    )
    payload = response.get_json()
    assert payload["is_available"] is False
    assert payload["message"]
