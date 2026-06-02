from pathlib import Path
from uuid import uuid4

from app.auth import AuthUser, SessionManager, UserStore


TEST_DATA_DIR = Path(__file__).resolve().parents[1] / ".tmp" / "auth-tests"


def _test_path(name: str) -> Path:
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return TEST_DATA_DIR / f"{name}-{uuid4().hex}.json"


def test_default_admin_is_seeded_and_verified() -> None:
    store = UserStore(_test_path("users"), default_username="admin", default_password="secret123")

    user = store.verify_user("admin", "secret123")

    assert user is not None
    assert user.username == "admin"
    assert user.role == "admin"
    assert store.verify_user("admin", "wrong") is None


def test_user_can_be_created_and_disabled() -> None:
    store = UserStore(_test_path("users"), default_username="admin", default_password="secret123")

    created = store.create_user("cliente", "cliente123", "viewer")
    store.set_active("cliente", False)

    assert created.username == "cliente"
    assert store.verify_user("cliente", "cliente123") is None
    assert store.get_user("cliente").active is False


def test_seed_users_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "ARBITRAGE_SEED_USERS",
        '[{"username":"tester1","password":"tester123","role":"viewer"}]',
    )
    store = UserStore(_test_path("users"), default_username="admin", default_password="secret123")

    seeded = store.verify_user("tester1", "tester123")

    assert seeded is not None
    assert seeded.username == "tester1"
    assert seeded.role == "viewer"


def test_session_manager_rejects_tampered_token() -> None:
    manager = SessionManager(_test_path("session-secret"), secret="test-secret")
    token = manager.create_token(AuthUser(username="admin", role="admin", active=True))
    tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"

    assert manager.verify_token(token).username == "admin"
    assert manager.verify_token(tampered) is None
