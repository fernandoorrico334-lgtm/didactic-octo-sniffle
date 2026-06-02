from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SESSION_COOKIE_NAME = "arbitrage_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


@dataclass(frozen=True, slots=True)
class AuthUser:
    username: str
    role: str
    active: bool


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def hash_password(password: str, *, iterations: int = 210_000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64_decode(salt_raw)
        expected = _b64_decode(digest_raw)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


class UserStore:
    def __init__(
        self,
        path: Path,
        *,
        default_username: str = "admin",
        default_password: str = "admin123",
    ) -> None:
        self.path = path
        self.default_username = default_username
        self.default_password = default_password

    def ensure_default_admin(self) -> None:
        users = self._read_users(create_if_missing=False)
        changed = False
        if any(user.get("role") == "admin" and user.get("active", True) for user in users):
            changed = self._seed_env_users(users)
        else:
            users.append(
                {
                    "username": self.default_username,
                    "password_hash": hash_password(self.default_password),
                    "role": "admin",
                    "active": True,
                    "created_at": int(time.time()),
                }
            )
            changed = True
            changed = self._seed_env_users(users) or changed

        if changed:
            self._write_users(users)

    def list_users(self) -> list[AuthUser]:
        self.ensure_default_admin()
        return [
            AuthUser(username=str(user["username"]), role=str(user["role"]), active=bool(user.get("active", True)))
            for user in sorted(self._read_users(), key=lambda item: str(item.get("username", "")).lower())
        ]

    def get_user(self, username: str) -> AuthUser | None:
        self.ensure_default_admin()
        user = self._find_user(username)
        if not user:
            return None
        return AuthUser(username=str(user["username"]), role=str(user["role"]), active=bool(user.get("active", True)))

    def verify_user(self, username: str, password: str) -> AuthUser | None:
        self.ensure_default_admin()
        user = self._find_user(username)
        if not user or not user.get("active", True):
            return None
        if not verify_password(password, str(user.get("password_hash", ""))):
            return None
        return AuthUser(username=str(user["username"]), role=str(user["role"]), active=True)

    def create_user(self, username: str, password: str, role: str) -> AuthUser:
        self.ensure_default_admin()
        username = username.strip()
        role = role.strip().lower()
        if not _USERNAME_RE.match(username):
            raise ValueError("Use um usuario com 3 a 32 caracteres: letras, numeros, ponto, traco ou underline.")
        if len(password) < 6:
            raise ValueError("A senha precisa ter pelo menos 6 caracteres.")
        if role not in {"admin", "viewer"}:
            raise ValueError("Perfil invalido.")
        users = self._read_users()
        if any(str(user.get("username", "")).lower() == username.lower() for user in users):
            raise ValueError("Esse usuario ja existe.")

        record = {
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "active": True,
            "created_at": int(time.time()),
        }
        users.append(record)
        self._write_users(users)
        return AuthUser(username=username, role=role, active=True)

    def set_active(self, username: str, active: bool) -> AuthUser:
        self.ensure_default_admin()
        users = self._read_users()
        for user in users:
            if str(user.get("username", "")).lower() == username.lower():
                if not active and user.get("role") == "admin" and self._active_admin_count(users) <= 1:
                    raise ValueError("Mantenha pelo menos um administrador ativo.")
                user["active"] = active
                self._write_users(users)
                return AuthUser(username=str(user["username"]), role=str(user["role"]), active=active)
        raise ValueError("Usuário não encontrado.")

    def _find_user(self, username: str) -> dict[str, Any] | None:
        username_lower = username.strip().lower()
        for user in self._read_users():
            if str(user.get("username", "")).lower() == username_lower:
                return user
        return None

    def _read_users(self, *, create_if_missing: bool = True) -> list[dict[str, Any]]:
        if not self.path.exists():
            if create_if_missing:
                self._write_users([])
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _write_users(self, users: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")

    def _seed_env_users(self, users: list[dict[str, Any]]) -> bool:
        raw = os.getenv("ARBITRAGE_SEED_USERS", "").strip()
        if not raw:
            return False
        seed_users = json.loads(raw)
        if not isinstance(seed_users, list):
            raise ValueError("ARBITRAGE_SEED_USERS precisa ser uma lista JSON.")

        existing = {str(user.get("username", "")).lower() for user in users}
        changed = False
        for seed in seed_users:
            if not isinstance(seed, dict):
                raise ValueError("Cada usuario em ARBITRAGE_SEED_USERS precisa ser um objeto JSON.")
            username = str(seed.get("username", "")).strip()
            password = str(seed.get("password", ""))
            role = str(seed.get("role", "viewer")).strip().lower()
            if username.lower() in existing:
                continue
            if not _USERNAME_RE.match(username):
                raise ValueError(f"Usuario invalido em ARBITRAGE_SEED_USERS: {username!r}.")
            if len(password) < 6:
                raise ValueError(f"Senha muito curta para usuario {username!r}.")
            if role not in {"admin", "viewer"}:
                raise ValueError(f"Perfil invalido para usuario {username!r}.")
            users.append(
                {
                    "username": username,
                    "password_hash": hash_password(password),
                    "role": role,
                    "active": True,
                    "created_at": int(time.time()),
                }
            )
            existing.add(username.lower())
            changed = True
        return changed

    @staticmethod
    def _active_admin_count(users: list[dict[str, Any]]) -> int:
        return sum(1 for user in users if user.get("role") == "admin" and user.get("active", True))


class SessionManager:
    def __init__(self, secret_path: Path, *, secret: str | None = None) -> None:
        self.secret_path = secret_path
        self._secret = (secret or os.getenv("ARBITRAGE_SESSION_SECRET") or "").encode("utf-8")

    @property
    def secret(self) -> bytes:
        if self._secret:
            return self._secret
        if self.secret_path.exists():
            self._secret = self.secret_path.read_text(encoding="utf-8").strip().encode("utf-8")
        else:
            self.secret_path.parent.mkdir(parents=True, exist_ok=True)
            self._secret = secrets.token_urlsafe(48).encode("utf-8")
            self.secret_path.write_text(self._secret.decode("utf-8"), encoding="utf-8")
        return self._secret

    def create_token(self, user: AuthUser, *, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
        payload = {
            "username": user.username,
            "role": user.role,
            "exp": int(time.time()) + ttl_seconds,
        }
        body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = _b64_encode(hmac.new(self.secret, body.encode("ascii"), hashlib.sha256).digest())
        return f"{body}.{signature}"

    def verify_token(self, token: str | None) -> AuthUser | None:
        if not token or "." not in token:
            return None
        body, signature = token.rsplit(".", 1)
        expected = _b64_encode(hmac.new(self.secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(_b64_decode(body).decode("utf-8"))
            if int(payload.get("exp", 0)) < int(time.time()):
                return None
            return AuthUser(username=str(payload["username"]), role=str(payload["role"]), active=True)
        except (ValueError, KeyError, TypeError):
            return None


def public_user(user: AuthUser) -> dict[str, str | bool]:
    return asdict(user)
