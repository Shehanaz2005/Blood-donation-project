"""Public pages and health checks."""
from __future__ import annotations


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Blood" in response.data
    assert b"Find Donors" in response.data


def test_about_page_loads(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert b"Frequently asked" in response.data or b"FAQ" in response.data


def test_find_donors_page_loads(client):
    response = client.get("/find-donors")
    assert response.status_code == 200
    assert b"donorSearchForm" in response.data


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "database": "up"}


def test_custom_404(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert b"Page not found" in response.data


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
