from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.auth import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, AuthUser, SessionManager, UserStore
from app.services.scanner import MarketScanner
from app.settings import PROJECT_ROOT, load_settings
from app.utils import dataclass_to_dict


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

CONFIG_PATH = os.getenv("ARBITRAGE_CONFIG")
settings = load_settings(CONFIG_PATH)
scanner = MarketScanner(settings)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _project_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


user_store = UserStore(
    _project_path(os.getenv("ARBITRAGE_USERS_PATH", PROJECT_ROOT / "config" / "users.json")),
    default_username=os.getenv("ARBITRAGE_ADMIN_USER", "admin"),
    default_password=os.getenv("ARBITRAGE_ADMIN_PASSWORD", "admin123"),
)
session_manager = SessionManager(
    _project_path(os.getenv("ARBITRAGE_SESSION_SECRET_PATH", PROJECT_ROOT / "config" / "session_secret.txt"))
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    user_store.ensure_default_admin()
    if settings.scanner.autostart:
        await scanner.start_background()
    yield
    await scanner.stop_background()


app = FastAPI(
    title="ArbFlow",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


async def _read_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _current_user(request: Request) -> AuthUser | None:
    session = session_manager.verify_token(request.cookies.get(SESSION_COOKIE_NAME))
    if not session:
        return None
    user = user_store.get_user(session.username)
    if not user or not user.active:
        return None
    return user


def _require_api_user(request: Request) -> AuthUser:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login obrigatório.")
    return user


def _require_admin_user(request: Request) -> AuthUser | None:
    user = _current_user(request)
    if not user or user.role != "admin":
        return None
    return user


def _set_session_cookie(response: RedirectResponse, user: AuthUser) -> None:
    secure_cookie = os.getenv("ARBITRAGE_SECURE_COOKIES", "").lower() in {"1", "true", "yes", "on"}
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_manager.create_token(user),
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        samesite="lax",
        secure=secure_cookie,
    )


def _market_feed_item(market: Any) -> dict[str, Any]:
    volume = market.volume_24h or 0.0
    liquidity = market.liquidity or 0.0
    return {
        "venue": market.venue,
        "title": market.question,
        "ticker": market.display_id,
        "url": market.url,
        "yes_ask": market.yes_ask,
        "no_ask": market.no_ask,
        "liquidity": liquidity,
        "volume_24h": volume,
        "score": max(volume, liquidity),
    }


def _market_feed(markets: list[Any], limit: int = 5) -> list[dict[str, Any]]:
    items = [_market_feed_item(market) for market in markets if market.question]
    items.sort(key=lambda item: item["score"], reverse=True)
    for item in items:
        item.pop("score", None)
    return items[:limit]


def _admin_page(
    request: Request,
    user: AuthUser,
    *,
    error: str | None = None,
    message: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "current_user": user,
            "users": user_store.list_users(),
            "error": error,
            "message": message,
        },
        status_code=status_code,
    )


@app.get("/healthz")
@app.head("/healthz")
async def render_healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.head("/")
@app.head("/login")
async def render_head_healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "data_mode": settings.scanner.data_mode,
            "project_root": str(PROJECT_ROOT),
            "current_user": user,
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _current_user(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login(request: Request):
    form = await _read_form(request)
    user = user_store.verify_user(form.get("username", ""), form.get("password", ""))
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Usuário ou senha inválidos."},
            status_code=401,
        )
    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, user)
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    user = _require_admin_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    return _admin_page(request, user)


@app.post("/admin/users")
async def create_admin_user(request: Request):
    user = _require_admin_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    form = await _read_form(request)
    try:
        user_store.create_user(
            username=form.get("username", ""),
            password=form.get("password", ""),
            role=form.get("role", "viewer"),
        )
    except ValueError as exc:
        return _admin_page(request, user, error=str(exc), status_code=400)
    return _admin_page(request, user, message="Usuário criado com sucesso.")


@app.post("/admin/users/{username}/toggle")
async def toggle_admin_user(username: str, request: Request):
    user = _require_admin_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    target = user_store.get_user(username)
    if not target:
        return _admin_page(request, user, error="Usuário não encontrado.", status_code=404)
    try:
        user_store.set_active(username, not target.active)
    except ValueError as exc:
        return _admin_page(request, user, error=str(exc), status_code=400)
    return _admin_page(request, user, message="Usuário atualizado.")


@app.get("/api/health")
async def health(request: Request) -> dict:
    _require_api_user(request)
    snapshot = scanner.latest()
    return {
        "status": snapshot.status,
        "updated_at": snapshot.updated_at,
        "error": snapshot.error,
        "data_mode": settings.scanner.data_mode,
        "counts": {
            "polymarket": snapshot.polymarket_count,
            "kalshi": snapshot.kalshi_count,
            "pairs": snapshot.pair_count,
            "signals": snapshot.signal_count,
        },
        "fees": {
            "polymarket_bps": settings.scanner.polymarket_fee_bps,
            "kalshi_bps": settings.scanner.kalshi_fee_bps,
            "included": (settings.scanner.polymarket_fee_bps + settings.scanner.kalshi_fee_bps) > 0,
        },
    }


@app.post("/api/scan")
async def scan_now(request: Request) -> dict:
    _require_api_user(request)
    snapshot = await scanner.scan_once()
    return dataclass_to_dict(snapshot)


@app.get("/api/signals")
async def signals(request: Request) -> dict:
    _require_api_user(request)
    snapshot = scanner.latest()
    return {
        "updated_at": snapshot.updated_at,
        "status": snapshot.status,
        "error": snapshot.error,
        "signals": dataclass_to_dict(snapshot.signals),
    }


@app.get("/api/pairs")
async def pairs(request: Request) -> dict:
    _require_api_user(request)
    snapshot = scanner.latest()
    return {
        "updated_at": snapshot.updated_at,
        "pairs": dataclass_to_dict(snapshot.pairs),
    }


@app.get("/api/markets")
async def markets(request: Request) -> dict:
    _require_api_user(request)
    snapshot = scanner.latest()
    return {
        "updated_at": snapshot.updated_at,
        "polymarket": dataclass_to_dict(snapshot.polymarket_markets),
        "kalshi": dataclass_to_dict(snapshot.kalshi_markets),
    }


@app.get("/api/market-feed")
async def market_feed(request: Request) -> dict:
    _require_api_user(request)
    snapshot = scanner.latest()
    return {
        "updated_at": snapshot.updated_at,
        "status": snapshot.status,
        "polymarket": _market_feed(snapshot.polymarket_markets),
        "kalshi": _market_feed(snapshot.kalshi_markets),
    }
