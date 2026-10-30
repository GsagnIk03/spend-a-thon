import os

# A real Postgres is required (CI starts one as a service; locally use Docker or any Postgres).
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5433/spendathon_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    from app import db
    from app.main import app

    engine = db.get_engine()
    db.metadata.drop_all(engine)
    db.reset_schema_flag()
    yield TestClient(app)
    engine.dispose()


def register(client, email="sagnik@example.com", name="Sagnik"):
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": "secret123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def auth(client):
    return register(client)
