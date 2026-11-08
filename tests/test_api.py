"""Versioned JSON API behaviour."""
from __future__ import annotations

from datetime import date, timedelta

from conftest import login


def test_api_requires_authentication(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "authentication_required"


def test_api_donor_list_shape(client, make_donor):
    make_donor(email="apilist@example.com", blood_group="O+")
    response = client.get("/api/v1/donors")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)
    assert payload["meta"]["page"] == 1
    assert "phone" not in payload["data"][0]


def test_api_blood_groups(client, make_donor):
    make_donor(email="apigroups@example.com", blood_group="A+")
    response = client.get("/api/v1/blood-groups")
    payload = response.get_json()
    assert response.status_code == 200
    groups = {item["group"]: item for item in payload["data"]}
    assert set(groups) == {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    assert groups["A+"]["donors"] == 1


def test_api_create_and_accept_request(client, app, make_receiver, make_donor):
    receiver = make_receiver(email="apireceiver@example.com")
    donor = make_donor(email="apidonor@example.com", phone="+2348055555555")
    login(client, receiver.email)

    payload = {
        "donor_id": donor.id,
        "units": 2,
        "urgency": "critical",
        "hospital_name": "City Hospital",
        "hospital_address": "10 Care Road",
        "city": "Lagos",
        "needed_by": (date.today() + timedelta(days=1)).isoformat(),
        "contact_phone": "+2348011113333",
        "message": "Please help.",
    }
    response = client.post("/api/v1/requests", json=payload)
    assert response.status_code == 201
    created = response.get_json()["data"]
    assert created["status"] == "pending"
    assert created["donor"]["phone"] is None
    request_id = created["id"]

    donor_client = app.test_client()
    login(donor_client, donor.email)
    response = donor_client.patch(
        f"/api/v1/requests/{request_id}/status",
        json={"action": "accept", "note": "On my way."},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "accepted"

    response = client.get(f"/api/v1/requests/{request_id}")
    payload = response.get_json()["data"]
    assert payload["status"] == "accepted"
    assert payload["donor"]["phone"] == donor.phone
    assert payload["donor"]["contact_visible"] is True


def test_api_create_request_validation(client, make_receiver, make_donor):
    receiver = make_receiver(email="apireceiver2@example.com")
    donor = make_donor(email="apidonor2@example.com")
    login(client, receiver.email)

    response = client.post(
        "/api/v1/requests",
        json={
            "donor_id": donor.id,
            "units": 99,
            "urgency": "urgent",
            "hospital_name": "City Hospital",
            "city": "Lagos",
            "contact_phone": "+2348011113333",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_api_donor_cannot_create_request(client, make_donor):
    donor = make_donor(email="apidonor3@example.com")
    login(client, donor.email)
    response = client.post("/api/v1/requests", json={"donor_id": donor.id})
    assert response.status_code == 403


def test_api_unverified_donor_cannot_be_requested(client, make_receiver, make_donor):
    receiver = make_receiver(email="apireceiver3@example.com")
    donor = make_donor(email="apidonor4@example.com", is_verified=False)
    login(client, receiver.email)

    response = client.post(
        "/api/v1/requests",
        json={
            "donor_id": donor.id,
            "units": 1,
            "urgency": "urgent",
            "hospital_name": "City Hospital",
            "city": "Lagos",
            "needed_by": (date.today() + timedelta(days=1)).isoformat(),
            "contact_phone": "+2348011113333",
        },
    )
    assert response.status_code == 400
    assert "verification" in response.get_json()["error"]["message"].lower()


def test_api_availability_toggle(client, make_donor):
    donor = make_donor(email="apidonor5@example.com")
    login(client, donor.email)

    response = client.post("/api/v1/donor/availability", json={"available": False})
    assert response.status_code == 200
    assert response.get_json()["data"]["is_available"] is False


def test_api_notifications(client, app, make_receiver, make_donor):
    receiver = make_receiver(email="apireceiver4@example.com")
    donor = make_donor(email="apidonor6@example.com")
    login(client, receiver.email)
    client.post(
        "/api/v1/requests",
        json={
            "donor_id": donor.id,
            "units": 1,
            "urgency": "urgent",
            "hospital_name": "City Hospital",
            "city": "Lagos",
            "needed_by": (date.today() + timedelta(days=1)).isoformat(),
            "contact_phone": "+2348011113333",
        },
    )

    donor_client = app.test_client()
    login(donor_client, donor.email)
    response = donor_client.get("/api/v1/notifications")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["meta"]["unread"] >= 1
    assert any(item["category"] == "request" for item in payload["data"])

    response = donor_client.post("/api/v1/notifications/read-all")
    assert response.status_code == 200
    assert response.get_json()["data"]["updated"] >= 1

    response = donor_client.get("/api/v1/notifications")
    assert response.get_json()["meta"]["unread"] == 0


def test_api_me(client, make_donor):
    donor = make_donor(email="apime@example.com", blood_group="AB+")
    login(client, donor.email)

    response = client.get("/api/v1/me")
    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["role"] == "donor"
    assert payload["donor"]["blood_group"] == "AB+"
    assert payload["email"] == donor.email
