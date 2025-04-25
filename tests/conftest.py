# tests/conftest.py
import pytest
import os
import requests

@pytest.fixture(scope="session")
def auth_service_url():
    """Fixture for the Auth Service URL."""
    return os.environ.get("AUTH_SERVICE_URL", "http://localhost:8081")

@pytest.fixture(scope="session")
def db_interact_url():
    """Fixture for the DB Interact Service URL."""
    return os.environ.get("DB_INTERACT_URL", "http://localhost:8082") # Adjust port if needed

@pytest.fixture(scope="session")
def http_session():
    """Provides a requests session for making HTTP calls."""
    # You could add default headers or other session configurations here if needed
    with requests.Session() as session:
        session.headers.update({"Content-Type": "application/json"})
        yield session

