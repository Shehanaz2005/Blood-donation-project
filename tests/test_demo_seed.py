"""The optional demo seeder must produce accounts that can actually sign in."""
from __future__ import annotations

from conftest import login


def test_demo_seed_accounts_can_sign_in(app, client):
    from demo_seed import DEMO_PASSWORD, seed_demo_data

    summary = seed_demo_data()
    assert summary["skipped"] is False
    assert summary["donors"] == 12
    assert summary["receivers"] == 3
    assert summary["requests"] == 6

    response = login(client, "demo.donor1@example.com", DEMO_PASSWORD)
    assert response.status_code == 200
    assert b"Hello, Amina" in response.data


def test_demo_seed_is_idempotent(app, client):
    from demo_seed import seed_demo_data

    seed_demo_data()
    second = seed_demo_data()
    assert second["skipped"] is True
    assert second["donors"] == 0
