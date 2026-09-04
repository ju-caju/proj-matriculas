"""FastAPI application for the local and Vercel runtimes."""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
)

from .sessions import MemorySessionStore, SessionStore
from .sigaa import Sigaa, SigaaClient
from .web import ROOT, SECURITY_HEADERS

MAX_JSON_BODY = 8192
CONFIGURATION_ERROR = {"error": "Serviço temporariamente indisponível."}
LOG_ALLOWED_FIELDS = frozenset(("event", "route", "status", "result", "duration_ms"))
_LOG_ROUTES = frozenset(
    (
        "/",
        "/app.js",
        "/schedule.js",
        "/style.css",
        "/health",
        "/api/health",
        "/api/session",
        "/api/login",
        "/api/logout",
        "/api/units",
        "/api/turmas",
    )
)
logger = logging.getLogger("matriculas.http")


def _safe_route(request: Request) -> str:
    path = request.scope.get("path", "")
    if isinstance(path, str) and path in _LOG_ROUTES:
        return path
    return "/unknown"


def _result_class(status: int) -> str:
    if 200 <= status < 300:
        return "ok"
    if status == 401:
        return "authentication"
    if status == 429:
        return "rate_limited"
    if 400 <= status < 500:
        return "rejected"
    if status == 503:
        return "dependency_unavailable"
    return "error"


def _log_request(request: Request, status: int, started: float) -> None:
    payload = {
        "event": "http_request",
        "route": _safe_route(request),
        "status": status,
        "result": _result_class(status),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    logger.info(
        json.dumps(
            {key: value for key, value in payload.items() if key in LOG_ALLOWED_FIELDS},
            separators=(",", ":"),
            ensure_ascii=True,
        )
    )


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
    discipline: StrictStr | None = Field(default=None, max_length=60)
    teacher: StrictStr | None = Field(default=None, max_length=60)

    @field_validator("year")
    @classmethod
    def valid_year(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"20\d{2}", value):
            raise ValueError("ano inválido")
        return value

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str | None) -> str | None:
        if value is not None and value not in ("0", "1", "2", "3", "4"):
            raise ValueError("período inválido")
        return value

    @field_validator("unit")
    @classmethod
    def valid_unit(cls, value: str | None) -> str | None:
        if value is not None and value and not value.isdigit():
            raise ValueError("unidade inválida")
        return value

    @field_validator("discipline", "teacher", mode="before")
    @classmethod
    def normalize_filter(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
        return value


class OkResponse(BaseModel):
    ok: bool


class UnitResponse(BaseModel):
    value: str
    label: str


class UnitsResponse(BaseModel):
    units: list[UnitResponse]


class QueryResponse(BaseModel):
    rows: list[dict[str, str]]
    units: list[UnitResponse]


CLASS_FIELDS = (
    "disciplina",
    "periodo",
    "turma",
    "docente",
    "tipo",
    "forma",
    "situacao",
    "horario",
    "local",
    "vagas",
)


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


def unavailable_app() -> FastAPI:
    """Return a closed-by-default app for an invalid production configuration.

    Vercel imports the module before it can serve a request.  Keeping an ASGI
    object available lets that import succeed while every request remains a
    generic 503, without accidentally falling back to local in-memory state.
    """

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            for key, value in SECURITY_HEADERS:
                response.headers[key] = value
            return response
        finally:
            _log_request(request, response.status_code if response else 500, started)

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    def unavailable() -> JSONResponse:
        return JSONResponse(status_code=503, content=CONFIGURATION_ERROR)

    return app


def _operation_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, PermissionError):
        return _error(401, str(exc))
    if isinstance(exc, ValueError):
        return _error(400, "Dados inválidos ou resposta inesperada do SIGAA.")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return _error(503, "Serviço temporariamente indisponível.")
    return _error(502, "Não foi possível consultar o SIGAA. Tente novamente.")


def _body_is_too_large(request: Request) -> bool:
    """Reject oversized JSON before FastAPI parses credentials or other fields."""
    value = request.headers.get("content-length")
    if value is None:
        return False
    try:
        return int(value) > MAX_JSON_BODY
    except ValueError:
        return True


def _units_response(value: Any) -> UnitsResponse:
    """Validate and project the SIGAA unit data to the public contract."""
    if not isinstance(value, list):
        raise ValueError("Unidades inválidas.")
    units: list[UnitResponse] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("value"), str)
            or not isinstance(item.get("label"), str)
        ):
            raise ValueError("Unidades inválidas.")
        units.append(UnitResponse(value=item["value"], label=item["label"]))
    return UnitsResponse(units=units)


def _query_response(value: Any) -> QueryResponse:
    """Validate and project query results before they can reach the browser."""
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise ValueError("Turmas inválidas.")
    rows = []
    for item in value["rows"]:
        if not isinstance(item, dict) or any(
            field not in item for field in CLASS_FIELDS
        ):
            raise ValueError("Turmas inválidas.")
        row = {}
        for field in CLASS_FIELDS:
            if not isinstance(item[field], str):
                raise ValueError("Turmas inválidas.")
            row[field] = item[field]
        rows.append(row)
    units = _units_response(value.get("units"))
    return QueryResponse(rows=rows, units=units.units)


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
        started = time.perf_counter()
        response = None
        try:
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
            elif request.method == "POST" and _body_is_too_large(request):
                response = _error(
                    400, "Dados inválidos ou resposta inesperada do SIGAA."
                )
            else:
                response = await call_next(request)

            response.headers["Cache-Control"] = "no-store"
            for key, value in SECURITY_HEADERS:
                response.headers[key] = value
            return response
        finally:
            _log_request(request, response.status_code if response else 500, started)

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

    @app.get("/frontend/{filename}")
    def frontend_script(filename: str) -> Response:
        if filename not in {
            "dom.js",
            "plan-store.js",
            "api-client.js",
            "grade-image.js",
        }:
            return _error(404, "Arquivo não encontrado.")
        return static_file("frontend/" + filename, "text/javascript")

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
            if login_limiter is not None:
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
            result = _units_response(client.units())
            if not session_store.refresh(session_id):
                raise PermissionError("Sua sessão expirou. Entre novamente.")
            return result
        except Exception as exc:
            return _operation_error(exc)

    @app.post("/api/turmas", response_model=QueryResponse)
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
            if not year or not period:
                raise ValueError("Confira ano, período e unidade.")
            result = _query_response(
                client.query(year, period, unit, discipline, teacher)
            )
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
