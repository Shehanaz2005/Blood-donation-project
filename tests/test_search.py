"""Donor directory search, filters and contact privacy."""
from __future__ import annotations

from datetime import date, timedelta

from conftest import login
from models import BloodRequest


def test_search_defaults_only_show_available_verified_eligible(client, make_donor):
    make_donor(email="visible@example.com", blood_group="A+", city="Lagos")
    make_donor(email="unverified@example.com", blood_group="A+", city="Lagos", is_verified=False)
    make_donor(
        email="cooldown@example.com",
        blood_group="A+",
        city="Lagos",
        last_donation_date=date.today() - timedelta(days=10),
    )

    response = client.get("/find-donors")
    assert response.status_code == 200
    assert b"visible@example.com" not in response.data  # contact details never rendered
    assert b"Test Donor" in response.data

    api = client.get("/api/v1/donors")
    payload = api.get_json()
    assert payload["ok"] is True
    assert payload["meta"]["total"] == 1
    assert payload["data"][0]["is_verified"] is True
    assert payload["data"][0]["is_eligible"] is True


def test_search_blood_group_and_city_filters(client, make_donor):
    make_donor(email="apluslagos@example.com", blood_group="A+", city="Lagos")
    make_donor(email="bpluslagos@example.com", blood_group="B+", city="Lagos")
    make_donor(email="aplusabuja@example.com", blood_group="A+", city="Abuja")

    response = client.get(
        "/api/v1/donors", query_string={"blood_group": "A+", "city": "Lagos"}
    )
    payload = response.get_json()
    assert payload["meta"]["total"] == 1
    assert payload["data"][0]["city"] == "Lagos"
    assert payload["data"][0]["blood_group"] == "A+"


def test_compatible_groups_widen_search(client, make_donor):
    make_donor(email="apos@example.com", blood_group="A+")
    make_donor(email="aneg@example.com", blood_group="A-")
    make_donor(email="opos@example.com", blood_group="O+")
    make_donor(email="bpos@example.com", blood_group="B+")

    response = client.get(
        "/api/v1/donors",
        query_string={"blood_group": "A+", "compatible": "1"},
    )
    payload = response.get_json()
    groups = {item["blood_group"] for item in payload["data"]}
    assert groups == {"A+", "A-", "O+"}


def test_unverified_and_cooldown_donors_can_be_revealed(client, make_donor):
    make_donor(email="unverified@example.com", is_verified=False)
    make_donor(
        email="cooldown@example.com",
        last_donation_date=date.today() - timedelta(days=5),
    )

    response = client.get(
        "/api/v1/donors",
        query_string={"verified": "0", "eligible": "0", "available": "0"},
    )
    payload = response.get_json()
    assert payload["meta"]["total"] == 2


def test_search_api_never_returns_contact_details(client, make_donor):
    make_donor(email="private@example.com", phone="+2348099999999")
    payload = client.get("/api/v1/donors").get_json()
    card = payload["data"][0]
    assert "phone" not in card
    assert "email" not in card
    assert "address" not in card


def test_donor_detail_hides_contact_until_request_accepted(client, make_donor, make_receiver):
    donor = make_donor(email="contact@example.com", share_contact=True)
    receiver = make_receiver(email="viewer@example.com")

    response = client.get(f"/api/v1/donors/{donor.donor_profile.id}")
    detail = response.get_json()["data"]
    assert detail["contact_allowed"] is False
    assert detail["phone"] is None

    login(client, receiver.email)
    response = client.get(f"/api/v1/donors/{donor.donor_profile.id}")
    detail = response.get_json()["data"]
    assert detail["contact_allowed"] is False
    assert detail["phone"] is None


def test_donor_detail_reveals_contact_after_acceptance(
    client, make_donor, make_receiver, make_request
):
    donor = make_donor(email="contact2@example.com", share_contact=True)
    receiver = make_receiver(email="viewer2@example.com")
    make_request(receiver, donor, status="accepted")

    login(client, receiver.email)
    response = client.get(f"/api/v1/donors/{donor.donor_profile.id}")
    detail = response.get_json()["data"]
    assert detail["contact_allowed"] is True
    assert detail["phone"] == donor.phone


def test_contact_stays_hidden_when_donor_opts_out(
    client, make_donor, make_receiver, make_request
):
    donor = make_donor(email="contact3@example.com", share_contact=False)
    receiver = make_receiver(email="viewer3@example.com")
    make_request(receiver, donor, status="accepted")

    login(client, receiver.email)
    detail = client.get(f"/api/v1/donors/{donor.donor_profile.id}").get_json()["data"]
    assert detail["contact_allowed"] is False
    assert detail["phone"] is None


def test_donor_profile_page_loads(client, make_donor):
    donor = make_donor(email="profilepage@example.com")
    response = client.get(f"/donors/{donor.donor_profile.id}")
    assert response.status_code == 200
    assert donor.full_name.encode() in response.data


def test_cities_endpoint(client, make_donor):
    make_donor(email="city1@example.com", city="Lagos")
    make_donor(email="city2@example.com", city="Abuja")
    response = client.get("/api/v1/donors/cities")
    assert response.status_code == 200
    cities = response.get_json()["data"]
    assert "Lagos" in cities
    assert "Abuja" in cities


def test_search_requires_active_user(client, make_donor):
    donor = make_donor(email="inactive@example.com", is_active=False)
    payload = client.get("/api/v1/donors").get_json()
    assert payload["meta"]["total"] == 0
