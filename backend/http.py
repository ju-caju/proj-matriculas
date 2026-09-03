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
            return self.headers.get("Host") in (
                "127.0.0.1:8765",
                "localhost:8765",
            )

        def session(self):
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            session_id = cookies["session"].value if "session" in cookies else ""
            return session_id, sessions.get(session_id)

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
                return self.reply(200, {"authenticated": bool(self.session()[1])})
            if self.path not in files:
                return self.reply(404, {"error": "Não encontrado."})
            filename, mime = files[self.path]
            self.reply(
                200,
                (static_root / filename).read_bytes(),
                mime=mime + "; charset=utf-8",
            )

        def do_POST(self):
            if not self.valid_host() or self.headers.get("Origin") not in (
                None,
                "http://127.0.0.1:8765",
                "http://localhost:8765",
            ):
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
                session_id, client = self.session()
                if self.path == "/api/login":
                    if not all(
                        isinstance(data.get(key), str) and data[key]
                        for key in ("username", "password")
                    ):
                        raise ValueError("Informe usuário e senha.")
                    new_client = client_factory()
                    new_client.login(data["username"], data["password"])
                    sessions.delete(session_id)
                    session_id = sessions.create(new_client)
                    return self.reply(
                        200,
                        {"ok": True},
                        "session="
                        + session_id
                        + "; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800",
                    )
                if self.path == "/api/logout":
                    sessions.delete(session_id)
                    return self.reply(
                        200,
                        {"ok": True},
                        "session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
                    )
                if not client:
                    raise PermissionError("Entre para consultar as turmas.")
                if self.path == "/api/units":
                    return self.reply(200, {"units": client.units()})
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
                    return self.reply(
                        200,
                        client.query(year, period, unit, discipline, teacher),
                    )
                self.reply(404, {"error": "Não encontrado."})
            except PermissionError as exc:
                self.reply(401, {"error": str(exc)})
            except ValueError:
                self.reply(
                    400,
                    {"error": "Dados inválidos ou resposta inesperada do SIGAA."},
                )
            except Exception:
                self.reply(
                    502,
                    {"error": "Não foi possível consultar o SIGAA. Tente novamente."},
                )

    return Handler
