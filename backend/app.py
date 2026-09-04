"""FastAPI application used during the HTTP adapter expansion."""

import re
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, StrictStr

from .http import ROOT, SECURITY_HEADERS
from .sessions import MemorySessionStore, SessionStore
from .sigaa import Sigaa, SigaaClient


class HealthResponse(BaseModel):
    status: str


class SessionStateResponse(BaseModel):
    authenticated: bool
    expired: bool


class LoginRequest(BaseModel):
    username: StrictStr | None = None
    password: StrictStr | None = None


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class QueryRequest(BaseModel):
    year: StrictStr | None = None
    period: StrictStr | None = None
    unit: StrictStr | None = None
    discipline: StrictStr | None = None
    teacher: StrictStr | None = None


class OkResponse(BaseModel):
    ok: bool


class UnitResponse(BaseModel):
    value: str
    label: str


class UnitsResponse(BaseModel):
    units: list[UnitResponse]


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


def _operation_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, PermissionError):
        return _error(401, str(exc))
    if isinstance(exc, ValueError):
        return _error(400, "Dados inválidos ou resposta inesperada do SIGAA.")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return _error(503, "Serviço temporariamente indisponível.")
    return _error(502, "Não foi possível consultar o SIGAA. Tente novamente.")


def create_app(
    client_factory: Callable[[], SigaaClient] = Sigaa,
    sessions: SessionStore | None = None,
    static_root: Path = ROOT,
    login_limiter: Any = None,
    client_ip: Callable[[Request], str | None] | None = None,
    secure_cookie: bool = False,
    cookie_path: str = "/",
    valid_hosts: tuple[str, ...] = (
        "127.0.0.1:8765",
        "localhost:8765",
        "testserver",
    ),
    valid_origins: tuple[str | None, ...] = (
        None,
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ),
) -> FastAPI:
    """Create the ASGI app with all external state supplied by the caller."""

    session_store = sessions if sessions is not None else MemorySessionStore()
    static_root = Path(static_root)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_and_request_checks(request: Request, call_next):
        response = None
        if request.headers.get("host") not in valid_hosts:
            response = _error(403, "Host inválido.")
        elif (
            request.method == "POST"
            and request.headers.get("origin") not in valid_origins
        ):
            response = _error(403, "Origem inválida.")
        elif (
            request.method == "POST"
            and request.headers.get("content-type", "").split(";", 1)[0]
            != "application/json"
        ):
            response = _error(415, "JSON necessário.")
        else:
            response = await call_next(request)

        response.headers["Cache-Control"] = "no-store"
        for key, value in SECURITY_HEADERS:
            response.headers[key] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _error(400, "Dados inválidos ou resposta inesperada do SIGAA.")

    def session(request: Request, refresh: bool = True):
        session_id = request.cookies.get("session", "")
        return session_id, session_store.get(session_id, refresh=refresh)

    def session_cookie(session_id: str, max_age: int) -> str:
        parts = [
            "session=" + session_id,
            "HttpOnly",
            "SameSite=Strict",
            "Path=" + cookie_path,
            "Max-Age=" + str(max_age),
        ]
        if secure_cookie:
            parts.append("Secure")
        return "; ".join(parts)

    def response_with_cookie(response: Response, cookie: str) -> Response:
        response.headers["Set-Cookie"] = cookie
        return response

    @app.get("/health", response_model=HealthResponse)
    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    def static_file(filename: str, media_type: str) -> Response:
        return Response((static_root / filename).read_bytes(), media_type=media_type)

    @app.get("/")
    def index() -> Response:
        return static_file("index.html", "text/html")

    @app.get("/app.js")
    def app_script() -> Response:
        return static_file("app.js", "text/javascript")

    @app.get("/schedule.js")
    def schedule_script() -> Response:
        return static_file("schedule.js", "text/javascript")

    @app.get("/style.css")
    def stylesheet() -> Response:
        return static_file("style.css", "text/css")

    @app.get("/api/session", response_model=SessionStateResponse)
    def get_session_state(request: Request):
        try:
            authenticated = bool(session(request)[1])
        except (ConnectionError, TimeoutError, ValueError):
            return _error(503, "Serviço temporariamente indisponível.")
        return SessionStateResponse(
            authenticated=authenticated,
            expired=bool(request.headers.get("cookie")) and not authenticated,
        )

    @app.post("/api/login", response_model=OkResponse)
    def login(request: Request, payload: LoginRequest):
        try:
            session_id, client = session(request, refresh=False)
            if login_limiter:
                address = client_ip(request) if client_ip else None
                if not login_limiter.allow(address):
                    return _error(
                        429,
                        "Muitas tentativas de login. Tente novamente mais tarde.",
                    )
            if not isinstance(payload.username, str) or not payload.username:
                raise ValueError("Informe usuário e senha.")
            if not isinstance(payload.password, str) or not payload.password:
                raise ValueError("Informe usuário e senha.")
            new_client = client_factory()
            new_client.login(payload.username, payload.password)
            session_store.delete(session_id)
            new_session_id = session_store.create(new_client)
            response = JSONResponse(status_code=200, content={"ok": True})
            return response_with_cookie(response, session_cookie(new_session_id, 1800))
        except Exception as exc:
            return _operation_error(exc)

    @app.post("/api/logout", response_model=OkResponse)
    def logout(request: Request, payload: EmptyRequest):
        try:
            session_id, _ = session(request, refresh=False)
            session_store.delete(session_id)
            response = JSONResponse(status_code=200, content={"ok": True})
            return response_with_cookie(response, session_cookie("", 0))
        except Exception as exc:
            return _operation_error(exc)

    @app.post("/api/units", response_model=UnitsResponse)
    def units(request: Request, payload: EmptyRequest):
        try:
            session_id, client = session(request, refresh=False)
            if not client:
                if session_id:
                    raise PermissionError("Sua sessão expirou. Entre novamente.")
                raise PermissionError("Entre para consultar as turmas.")
            result = client.units()
            if not session_store.refresh(session_id):
                raise PermissionError("Sua sessão expirou. Entre novamente.")
            return UnitsResponse(units=result)
        except Exception as exc:
            return _operation_error(exc)

    @app.post("/api/turmas")
    def classes(request: Request, payload: QueryRequest):
        try:
            session_id, client = session(request, refresh=False)
            if not client:
                if session_id:
                    raise PermissionError("Sua sessão expirou. Entre novamente.")
                raise PermissionError("Entre para consultar as turmas.")
            year, period, unit = (
                str(getattr(payload, key) or "") for key in ("year", "period", "unit")
            )
            discipline, teacher = (
                str(getattr(payload, key) or "").strip()
                for key in ("discipline", "teacher")
            )
            if (
                not re.fullmatch(r"20\d{2}", year)
                or period not in ("0", "1", "2", "3", "4")
                or (unit and not unit.isdigit())
                or max(len(discipline), len(teacher)) > 60
            ):
                raise ValueError("Confira ano, período e unidade.")
            result = client.query(year, period, unit, discipline, teacher)
            if not session_store.refresh(session_id):
                raise PermissionError("Sua sessão expirou. Entre novamente.")
            return result
        except Exception as exc:
            return _operation_error(exc)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    def not_found() -> JSONResponse:
        return _error(404, "Não encontrado.")

    return app


make_app = create_app
app = create_app()
