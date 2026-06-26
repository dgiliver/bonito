"""Pytest configuration and shared fixtures."""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def credential_password():
    """Provide BONITO_CREDENTIAL_PASSWORD for the test session.

    Production code refuses to encrypt/decrypt broker credentials without
    this env var set (no hardcoded fallback) - tests need a value so any
    code path touching CredentialStore doesn't raise RuntimeError.
    """
    os.environ["BONITO_CREDENTIAL_PASSWORD"] = "test-password-not-for-prod"
    yield
    del os.environ["BONITO_CREDENTIAL_PASSWORD"]


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (network-dependent)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip slow tests unless --run-slow is provided."""
    if config.getoption("--run-slow"):
        return

    skip_slow = pytest.mark.skip(reason="Need --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
