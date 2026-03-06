import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base


# StaticPool forces all connections to reuse the same underlying connection,
# so every thread sees the same in-memory schema and data.
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


@contextmanager
def _mock_session():
    """Drop-in replacement for get_session that uses the shared in-memory DB."""
    session = _Session()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def test_db():
    session = _Session()
    try:
        yield session
    finally:
        session.close()


def test_stats_endpoint_empty_db():
    with patch("dashboard.app.get_session", _mock_session):
        from dashboard.app import app
        client = TestClient(app)
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert data["total"] == 0


def test_dashboard_returns_html():
    with patch("dashboard.app.get_session", _mock_session):
        from dashboard.app import app
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "OpenClaw Dashboard" in response.text

def test_mark_converted_not_found(test_db):
    @contextmanager
    def mock_session():
        yield test_db

    with patch("dashboard.app.get_session", mock_session):
        from dashboard.app import app
        client = TestClient(app)
        response = client.post("/api/mark-converted/99999")
        assert response.status_code == 404
