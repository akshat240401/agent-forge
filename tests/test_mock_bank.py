from fastapi.testclient import TestClient

from src.mock_bank.app import app


client = TestClient(app)


def test_search_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Legacy Member Servicing System" in response.text
    assert "Member ID" in response.text
    assert "data-testid" not in response.text


def test_valid_member_returns_accounts_and_savings_balance():
    response = client.post("/members/search", data={"member_id": "12345"})
    assert response.status_code == 200
    assert "Member Record" in response.text
    assert "Savings" in response.text
    assert "$4,821.37" in response.text


def test_unknown_member_is_business_outcome_page_not_server_error():
    response = client.post("/members/search", data={"member_id": "99999"})
    assert response.status_code == 200
    assert "No member found for ID 99999." in response.text


def test_slow_member_returns_known_recoverable_interstitial():
    response = client.post("/members/search", data={"member_id": "55555"})
    assert response.status_code == 200
    assert "Session Confirmation" in response.text
    assert "Continue Session" in response.text


def test_interstitial_can_be_recovered_to_member_details():
    response = client.post("/session/continue", data={"member_id": "12345"})
    assert response.status_code == 200
    assert "Member Record" in response.text
    assert "$4,821.37" in response.text


def test_permission_denied_is_explicit_hard_failure_surface():
    response = client.post("/members/search", data={"member_id": "77777"})
    assert response.status_code == 403
    assert "Access Denied" in response.text
    assert "do not have permission" in response.text
