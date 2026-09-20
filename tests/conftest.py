import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app
from app.seed import seed_database

PASSWORD = "test-password"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test gets its own brand-new database with claim C001 in 'draft'."""
    monkeypatch.setenv("NORTEX_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(auth, "PBKDF2_ITERATIONS", 1000)   # fast hashing in tests only
    seed_database(PASSWORD)


def client_for(emp_code: str, password: str = PASSWORD) -> TestClient:
    """A separate browser (its own cookie jar) logged in as this employee."""
    c = TestClient(app)
    res = c.post("/api/login", json={"emp_code": emp_code, "password": password})
    assert res.status_code == 200, res.text
    return c


CHAITANYA, SURESH, MEERA, ARVIND = "NX-4471", "NX-2210", "NX-1108", "NX-1002"
RAVI, KAVITHA, DEEPA = "NX-3305", "NX-3300", "NX-5182"


def act(client: TestClient, claim_id: str, action: str, remarks: str | None = None):
    return client.post(f"/api/claims/{claim_id}/actions", json={"action": action, "remarks": remarks})
