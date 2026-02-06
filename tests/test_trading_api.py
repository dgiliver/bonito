"""Tests for trading API endpoints."""

import pytest
from fastapi.testclient import TestClient

from bonito.api.main import app
from bonito.trading.bot_registry import BotRegistry

# Minimal valid strategy configs for testing
VALID_STRATEGY_CONFIG = {
    "name": "test_strategy",
    "symbols": ["SPY"],
    "entry_rules": [
        {"conditions": [{"left": "close", "comparison": "crosses_above", "right": "sma_20"}]}
    ],
}

STRATEGY_WITH_STOP_LOSS = {
    **VALID_STRATEGY_CONFIG,
    "stop_loss": {"type": "percent", "value": 0.05},
}


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset bot registry before each test."""
    BotRegistry.reset()
    yield
    BotRegistry.reset()


@pytest.fixture(autouse=True)
def reset_credentials():
    """Reset credential store before each test."""
    import bonito.api.routes.trading as trading_routes
    from bonito.trading.credential_store import CredentialStore

    # Use a test-specific credential store
    store = CredentialStore()
    if store.has_credentials():
        store.delete_credentials()

    # Clear the module-level cache in trading routes
    trading_routes._account_info = None

    yield

    # Clean up after test
    if store.has_credentials():
        store.delete_credentials()

    # Clear the cache again
    trading_routes._account_info = None


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def linked_client(client):
    """Create test client with linked credentials."""
    # Link credentials using mock mode
    import os

    os.environ["BONITO_USE_MOCK_ALPACA_API"] = "true"
    response = client.post(
        "/api/trading/account/link",
        json={
            "api_key": "PKABCDEFGHIJ12345678ABCD",
            "secret_key": "A" * 44,
            "is_paper": True,
        },
    )
    assert response.status_code == 200
    yield client
    # Clean up
    del os.environ["BONITO_USE_MOCK_ALPACA_API"]


class TestDeployBotEndpoint:
    def test_deploy_without_credentials(self, client):
        """Verify that deploying without credentials fails."""
        response = client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "momentum",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "mode": "paper",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )

        assert response.status_code == 400
        assert "No credentials linked" in response.json()["detail"]

    def test_deploy_paper_bot(self, linked_client):
        response = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "momentum",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "mode": "paper",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "bot_id" in data
        assert data["mode"] == "paper"
        assert data["status"] == "running"

    def test_deploy_high_risk_requires_acknowledgment(self, linked_client):
        response = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "risky",
                "strategy_config": VALID_STRATEGY_CONFIG,
                "execution_model": "continuous",
                "mode": "live",
                "max_position_pct": 95.0,
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Risk acknowledgment required" in data["detail"]["error"]

    def test_deploy_high_risk_with_acknowledgment(self, linked_client):
        response = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "risky",
                "strategy_config": VALID_STRATEGY_CONFIG,
                "execution_model": "continuous",
                "mode": "live",
                "max_position_pct": 95.0,
                "acknowledge_risks": True,
            },
        )

        assert response.status_code == 201


class TestListBotsEndpoint:
    def test_list_empty(self, client):
        response = client.get("/api/trading/bots")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_list_with_bots(self, linked_client):
        # Deploy a bot first (with safe config)
        linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )

        response = linked_client.get("/api/trading/bots")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1


class TestGetBotEndpoint:
    def test_get_not_found(self, client):
        response = client.get("/api/trading/bots/nonexistent")

        assert response.status_code == 404

    def test_get_existing(self, linked_client):
        # Deploy first (with safe config)
        deploy_response = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )
        bot_id = deploy_response.json()["bot_id"]

        response = linked_client.get(f"/api/trading/bots/{bot_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == bot_id


class TestPauseResumeStopEndpoints:
    def test_pause_bot(self, linked_client):
        # Deploy (with safe config)
        deploy = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )
        bot_id = deploy.json()["bot_id"]

        response = linked_client.post(f"/api/trading/bots/{bot_id}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    def test_resume_bot(self, linked_client):
        # Deploy and pause (with safe config)
        deploy = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )
        bot_id = deploy.json()["bot_id"]
        linked_client.post(f"/api/trading/bots/{bot_id}/pause")

        response = linked_client.post(f"/api/trading/bots/{bot_id}/resume")

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_stop_bot(self, linked_client):
        # Deploy (with safe config)
        deploy = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )
        bot_id = deploy.json()["bot_id"]

        response = linked_client.post(f"/api/trading/bots/{bot_id}/stop")

        assert response.status_code == 200
        assert response.json()["status"] == "stopped"


class TestModifyBotEndpoint:
    def test_modify_position_size(self, linked_client):
        # Deploy (with safe config)
        deploy = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )
        bot_id = deploy.json()["bot_id"]

        response = linked_client.put(
            f"/api/trading/bots/{bot_id}",
            json={
                "max_position_pct": 5.0,
            },
        )

        assert response.status_code == 200
        assert "max_position_pct" in response.json()["modified"]


class TestDeleteBotEndpoint:
    def test_delete_bot(self, linked_client):
        # Deploy (with safe config)
        deploy = linked_client.post(
            "/api/trading/bots",
            json={
                "strategy_name": "test",
                "strategy_config": STRATEGY_WITH_STOP_LOSS,
                "execution_model": "scheduled",
                "max_position_pct": 10.0,
                "max_daily_loss_pct": 5.0,
            },
        )
        bot_id = deploy.json()["bot_id"]

        response = linked_client.delete(f"/api/trading/bots/{bot_id}")

        assert response.status_code == 200

        # Verify deleted
        list_response = linked_client.get("/api/trading/bots")
        assert list_response.json()["total"] == 0


class TestAccountEndpoints:
    def test_get_account_not_linked(self, client):
        response = client.get("/api/trading/account")

        assert response.status_code == 200
        assert response.json()["linked"] is False

    def test_link_account_invalid_key(self, client):
        response = client.post(
            "/api/trading/account/link",
            json={
                "api_key": "invalid",
                "secret_key": "A" * 40,
                "is_paper": True,
            },
        )

        assert response.status_code == 400

    def test_link_account_valid(self, client):
        import os

        # Use mock API for validation
        os.environ["BONITO_USE_MOCK_ALPACA_API"] = "true"

        response = client.post(
            "/api/trading/account/link",
            json={
                "api_key": "PKABCDEFGHIJ12345678ABCD",
                "secret_key": "A" * 44,
                "is_paper": True,
            },
        )

        # Clean up
        del os.environ["BONITO_USE_MOCK_ALPACA_API"]

        assert response.status_code == 200
        data = response.json()
        assert data["linked"] is True
        assert "PKAB" in data["api_key_preview"]  # Redacted
        assert "GHIJ" not in data["api_key_preview"]  # Middle hidden


class TestSecurityRequirements:
    def test_no_secrets_in_response(self, client):
        """Verify credentials never appear in responses (for valid keys)."""
        response = client.post(
            "/api/trading/account/link",
            json={
                "api_key": "PKABCDEFGHIJ12345678ABCD",
                "secret_key": "SECRETKEYSECRETKEYSECRETKEYSECRETKEY12345678",
                "is_paper": True,
            },
        )

        response_text = response.text
        # Check that full API key is not in response (except in preview which is redacted)
        assert "PKABCDEFGHIJ12345678ABCD" not in response_text
        # Check secret key never appears
        assert "SECRETKEYSECRETKEYSECRETKEYSECRETKEY12345678" not in response_text
