from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_health_checks_database():
    connection = MagicMock()
    with patch("app.api.psycopg.connect") as connect:
        connect.return_value.__enter__.return_value = connection
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"api": "ok", "db": "ok"}
    connection.execute.assert_called_once_with("SELECT 1")


def test_database_failure_is_reported_without_leaking_credentials():
    with patch("app.api.psycopg.connect", side_effect=psycopg.OperationalError("secret")):
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"api": "ok", "db": "error"}
