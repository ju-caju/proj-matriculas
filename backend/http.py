import json
import re
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable

from .sessions import SessionStore
from .sigaa import SigaaClient


ROOT = Path(__file__).parent.parent


def make_handler(
    client_factory: Callable[[], SigaaClient],
    sessions: SessionStore,
    static_root=ROOT,
    login_limiter=None,
    client_ip=None,
    secure_cookie=False,
    cookie_path="/",
    valid_hosts=("127.0.0.1:8765", "localhost:8765"),
    valid_origins=(None, "http://127.0.0.1:8765", "http://localhost:8765"),
):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(
            self,
            status,
            body,
            cookie=None,
            mime="application/json; charset=utf-8",
        ):
            data = (
                body
                if isinstance(body, bytes)
                else json.dumps(body, ensure_ascii=False).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "frame-ancestors 'none'; form-action 'self'",
            )
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") in valid_hosts

        def session(self, refresh=True):
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            session_id = cookies["session"].value if "session" in cookies else ""
            return session_id, sessions.get(session_id, refresh=refresh)

        def session_cookie(self, session_id, max_age):
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

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {"error": "Host inválido."})
            files = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/schedule.js": ("schedule.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if self.path == "/api/session":
                try:
                    authenticated = bool(self.session()[1])
                except (ConnectionError, TimeoutError, ValueError):
                    return self.reply(
                        503, {"error": "Serviço temporariamente indisponível."}
                    )
                return self.reply(
                    200,
                    {
                        "authenticated": authenticated,
                        "expired": bool(self.headers.get("Cookie")) and not authenticated,
                    },
                )
            if self.path not in files:
                return self.reply(404, {"error": "Não encontrado."})
            filename, mime = files[self.path]
            self.reply(
                200,
                (static_root / filename).read_bytes(),
                mime=mime + "; charset=utf-8",
            )

        def do_POST(self):
            if not self.valid_host() or self.headers.get("Origin") not in valid_origins:
                return self.reply(403, {"error": "Origem inválida."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "JSON necessário."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Dados inválidos.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Dados inválidos.")
                session_id, client = self.session(refresh=False)
                if self.path == "/api/login":
                    if not all(
                        isinstance(data.get(key), str) and data[key]
                        for key in ("username", "password")
                    ):
                        raise ValueError("Informe usuário e senha.")
                    if login_limiter:
                        address = client_ip(self) if client_ip else None
                        if not login_limiter.allow(address):
                            return self.reply(
                                429,
                                {
                                    "error": "Muitas tentativas de login. "
                                    "Tente novamente mais tarde."
                                },
                            )
                    new_client = client_factory()
                    new_client.login(data["username"], data["password"])
                    sessions.delete(session_id)
                    session_id = sessions.create(new_client)
                    return self.reply(
                        200,
                        {"ok": True},
                        self.session_cookie(session_id, 1800),
                    )
                if self.path == "/api/logout":
                    sessions.delete(session_id)
                    return self.reply(
                        200,
                        {"ok": True},
                        self.session_cookie("", 0),
                    )
                if not client:
                    if session_id:
                        raise PermissionError("Sua sessão expirou. Entre novamente.")
                    raise PermissionError("Entre para consultar as turmas.")
                if self.path == "/api/units":
                    result = client.units()
                    if not sessions.refresh(session_id):
                        raise PermissionError("Sua sessão expirou. Entre novamente.")
                    return self.reply(200, {"units": result})
                if self.path == "/api/turmas":
                    year, period, unit = (
                        str(data.get(key, "")) for key in ("year", "period", "unit")
                    )
                    discipline, teacher = (
                        str(data.get(key, "")).strip()
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
                    if not sessions.refresh(session_id):
                        raise PermissionError("Sua sessão expirou. Entre novamente.")
                    return self.reply(200, result)
                self.reply(404, {"error": "Não encontrado."})
            except PermissionError as exc:
                self.reply(401, {"error": str(exc)})
            except ValueError:
                self.reply(
                    400,
                    {"error": "Dados inválidos ou resposta inesperada do SIGAA."},
                )
            except (ConnectionError, TimeoutError):
                self.reply(503, {"error": "Serviço temporariamente indisponível."})
            except Exception:
                self.reply(
                    502,
                    {"error": "Não foi possível consultar o SIGAA. Tente novamente."},
                )

    return Handler
