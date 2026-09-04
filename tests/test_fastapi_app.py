import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import create_app, unavailable_app
from backend.production import make_production_app
from backend.sessions import MemorySessionStore


class ControlledClient:
    def __init__(self, username="student"):
        self.username = username
        self.query_calls = []

    def login(self, username, password):
        self.username = username

    def units(self):
        return [{"value": "1", "label": self.username}]

    def query(self, year, period, unit, discipline="", teacher=""):
        self.query_calls.append((year, period, unit, discipline, teacher))
        return {"rows": [], "units": self.units()}


class MalformedUnitsClient(ControlledClient):
    def units(self):
        return [{"value": 2151, "label": "Unidade"}]


class UntrustedRowsClient(ControlledClient):
    def query(self, year, period, unit, discipline="", teacher=""):
        return {
            "rows": [
                {
                    "disciplina": "CÁLCULO",
                    "periodo": "2026.2",
                    "turma": "01",
                    "docente": "DOCENTE",
                    "tipo": "REGULAR",
                    "forma": "Presencial",
                    "situacao": "ABERTA",
                    "horario": "24M23",
                    "local": "SALA",
                    "vagas": "10 vagas",
                    "script": "javascript:acao()",
                }
            ],
            "units": self.units(),
        }


class FalseyLimiter:
    def __init__(self):
        self.calls = []

    def __bool__(self):
        return False

    def allow(self, address):
        self.calls.append(address)
        return True


class UnavailableLimiter:
    def allow(self, address):
        raise ConnectionError("rate limit unavailable")


class InvalidCredentialsClient(ControlledClient):
    def login(self, username, password):
        raise PermissionError("Login não confirmado.")


class FastApiTest(unittest.TestCase):
    def setUp(self):
        self.sessions = MemorySessionStore(token_factory=lambda: "session-id")
        self.clients = []

        def factory():
            client = ControlledClient()
            self.clients.append(client)
            return client

        self.app = create_app(
            client_factory=factory,
            sessions=self.sessions,
        )
        self.client = TestClient(self.app)

    def test_health_is_local_and_does_not_touch_session_store(self):
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())
        self.assertEqual("no-store", response.headers["cache-control"])
        self.assertEqual("nosniff", response.headers["x-content-type-options"])

    def test_unavailable_app_fails_closed_without_falling_back_to_memory(self):
        response = TestClient(unavailable_app()).get("/")

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            {"error": "Serviço temporariamente indisponível."}, response.json()
        )
        self.assertEqual("no-store", response.headers["cache-control"])
        self.assertEqual("DENY", response.headers["x-frame-options"])

    def test_page_and_static_files_are_served_from_same_app(self):
        for path, content_type in (
            ("/", "text/html; charset=utf-8"),
            ("/app.js", "text/javascript; charset=utf-8"),
            ("/schedule.js", "text/javascript; charset=utf-8"),
            ("/frontend/dom.js", "text/javascript; charset=utf-8"),
            ("/frontend/plan-store.js", "text/javascript; charset=utf-8"),
            ("/frontend/api-client.js", "text/javascript; charset=utf-8"),
            ("/frontend/course-filter.js", "text/javascript; charset=utf-8"),
            ("/frontend/grade-image.js", "text/javascript; charset=utf-8"),
            ("/style.css", "text/css; charset=utf-8"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                self.assertEqual(content_type, response.headers["content-type"])
                self.assertTrue(response.content)

    def test_session_state_preserves_absent_valid_and_expired_semantics(self):
        self.assertEqual(
            {"authenticated": False, "expired": False},
            self.client.get("/api/session").json(),
        )

        session_id = self.sessions.create(ControlledClient("alice"))
        self.client.cookies.set("session", session_id)
        self.assertEqual(
            {"authenticated": True, "expired": False},
            self.client.get("/api/session").json(),
        )

        self.sessions.delete(session_id)
        response = self.client.get("/api/session")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"authenticated": False, "expired": True}, response.json())

    def test_login_and_units_use_injected_dependencies_over_http(self):
        response = self.client.post(
            "/api/login", json={"username": "alice", "password": "secret"}
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True}, response.json())
        self.assertIn("SameSite=Strict", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])

        response = self.client.post("/api/units", json={})
        self.assertEqual(200, response.status_code)
        self.assertEqual({"units": [{"value": "1", "label": "alice"}]}, response.json())

    def test_authenticated_units_query_and_logout_use_fastapi_contract(self):
        login = self.client.post(
            "/api/login", json={"username": "alice", "password": "secret"}
        )
        self.assertEqual(200, login.status_code)

        response = self.client.post(
            "/api/turmas",
            json={
                "year": "2026",
                "period": "2",
                "unit": "2151",
                "discipline": " cálculo ",
                "teacher": " docente ",
            },
        )
        self.assertEqual(
            {"rows": [], "units": [{"value": "1", "label": "alice"}]},
            response.json(),
        )
        self.assertEqual(
            [("2026", "2", "2151", "cálculo", "docente")],
            self.clients[0].query_calls,
        )

        logout = self.client.post("/api/logout", json={})
        self.assertEqual(200, logout.status_code)
        self.assertEqual(401, self.client.post("/api/units", json={}).status_code)

    def test_query_validation_happens_before_gateway_call(self):
        self.client.post("/api/login", json={"username": "alice", "password": "secret"})

        for payload in (
            {"year": "20ab", "period": "2"},
            {"year": "2026", "period": "9"},
            {"year": "2026", "period": "2", "unit": "not-a-unit"},
            {"year": "2026", "period": "2", "teacher": "x" * 61},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/turmas", json=payload)
                self.assertEqual(400, response.status_code)
        self.assertEqual([], self.clients[0].query_calls)

    def test_unexpected_unit_data_is_controlled_before_session_refresh(self):
        sessions = MemorySessionStore(token_factory=lambda: "session-id")
        app = create_app(client_factory=MalformedUnitsClient, sessions=sessions)
        client = TestClient(app)
        self.assertEqual(
            200,
            client.post(
                "/api/login", json={"username": "alice", "password": "secret"}
            ).status_code,
        )
        response = client.post("/api/units", json={})
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"error": "Dados inválidos ou resposta inesperada do SIGAA."},
            response.json(),
        )

    def test_query_projection_does_not_expose_unexpected_fields(self):
        sessions = MemorySessionStore(token_factory=lambda: "session-id")
        app = create_app(client_factory=UntrustedRowsClient, sessions=sessions)
        client = TestClient(app)
        client.post("/api/login", json={"username": "alice", "password": "secret"})
        response = client.post("/api/turmas", json={"year": "2026", "period": "2"})
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    "disciplina": "CÁLCULO",
                    "periodo": "2026.2",
                    "turma": "01",
                    "docente": "DOCENTE",
                    "tipo": "REGULAR",
                    "forma": "Presencial",
                    "situacao": "ABERTA",
                    "horario": "24M23",
                    "local": "SALA",
                    "vagas": "10 vagas",
                }
            ],
            response.json()["rows"],
        )
        self.assertNotIn("script", response.text)

    def test_post_contract_rejects_non_json_and_keeps_security_headers(self):
        response = self.client.post("/api/logout", content="{}")

        self.assertEqual(415, response.status_code)
        self.assertEqual({"error": "JSON necessário."}, response.json())
        self.assertEqual("DENY", response.headers["x-frame-options"])

    def test_production_factory_exposes_fastapi_login_and_logout(self):
        environment = {
            "KV_REST_API_URL": "https://redis.example",
            "KV_REST_API_TOKEN": "token",
            "SESSION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "VERCEL_URL": "preview.example.vercel.app",
        }
        with patch("backend.production.RedisRestClient.execute"):
            app = make_production_app(environment)

        self.assertIsInstance(app, FastAPI)
        self.assertIn("/api/login", {route.path for route in app.routes})
        self.assertIn("/api/logout", {route.path for route in app.routes})

    def test_production_startup_uses_fastapi_and_controlled_redis(self):
        environment = {
            "KV_REST_API_URL": "https://redis.example",
            "KV_REST_API_TOKEN": "token",
            "SESSION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "VERCEL_URL": "preview.example.vercel.app",
        }
        with patch(
            "backend.sessions.RedisRestClient.execute",
            side_effect=ConnectionError("redis unavailable"),
        ):
            client = TestClient(make_production_app(environment))
            response = client.post(
                "/api/login",
                json={"username": "student", "password": "password"},
                headers={
                    "host": "preview.example.vercel.app",
                    "origin": "https://preview.example.vercel.app",
                    "x-vercel-forwarded-for": "203.0.113.10",
                },
            )

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            {"error": "Serviço temporariamente indisponível."}, response.json()
        )

    def test_login_uses_a_configured_limiter_even_when_it_is_falsey(self):
        limiter = FalseyLimiter()
        app = create_app(
            client_factory=lambda: ControlledClient(),
            sessions=MemorySessionStore(token_factory=lambda: "session-id"),
            login_limiter=limiter,
            client_ip=lambda request: "203.0.113.10",
        )

        response = TestClient(app).post(
            "/api/login", json={"username": "alice", "password": "secret"}
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(["203.0.113.10"], limiter.calls)

    def test_login_rejects_oversized_json_before_calling_gateway(self):
        response = self.client.post(
            "/api/login",
            content='{"username":"alice","password":"' + "x" * 8200 + '"}',
            headers={"content-type": "application/json"},
        )

        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"error": "Dados inválidos ou resposta inesperada do SIGAA."},
            response.json(),
        )
        self.assertEqual([], self.clients)

    def test_login_replaces_previous_session_and_logout_expires_it(self):
        identifiers = iter(("session-a", "session-b"))
        sessions = MemorySessionStore(token_factory=lambda: next(identifiers))
        clients = []

        def factory():
            client = ControlledClient()
            clients.append(client)
            return client

        client = TestClient(create_app(client_factory=factory, sessions=sessions))
        first = client.post(
            "/api/login", json={"username": "alice", "password": "secret"}
        )
        first_cookie = first.headers["set-cookie"].split(";", 1)[0]
        second = client.post(
            "/api/login", json={"username": "bob", "password": "secret"}
        )
        second_cookie = second.headers["set-cookie"].split(";", 1)[0]

        self.assertNotEqual(first_cookie, second_cookie)
        client.cookies.set("session", "session-a")
        self.assertEqual(401, client.post("/api/units", json={}).status_code)
        client.cookies.set("session", "session-b")
        self.assertEqual(
            {"units": [{"value": "1", "label": "bob"}]},
            client.post("/api/units", json={}).json(),
        )

        logout = client.post("/api/logout", json={})

        self.assertEqual(200, logout.status_code)
        self.assertIn("Max-Age=0", logout.headers["set-cookie"])
        self.assertEqual(401, client.post("/api/units", json={}).status_code)
        client.cookies.set("session", "session-b")
        self.assertEqual(
            {"authenticated": False, "expired": True},
            client.get("/api/session").json(),
        )
        self.assertEqual(["alice", "bob"], [item.username for item in clients])

    def test_rate_limit_dependency_failure_is_publicly_controlled(self):
        app = create_app(
            client_factory=lambda: ControlledClient(),
            sessions=MemorySessionStore(token_factory=lambda: "session-id"),
            login_limiter=UnavailableLimiter(),
            client_ip=lambda request: "203.0.113.10",
        )

        response = TestClient(app).post(
            "/api/login", json={"username": "alice", "password": "secret"}
        )

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            {"error": "Serviço temporariamente indisponível."}, response.json()
        )

    def test_invalid_credentials_keep_the_public_login_error_contract(self):
        app = create_app(
            client_factory=InvalidCredentialsClient,
            sessions=MemorySessionStore(token_factory=lambda: "session-id"),
        )

        response = TestClient(app).post(
            "/api/login", json={"username": "alice", "password": "wrong"}
        )

        self.assertEqual(401, response.status_code)
        self.assertEqual({"error": "Login não confirmado."}, response.json())
        self.assertNotIn("alice", response.text)
        self.assertNotIn("wrong", response.text)


if __name__ == "__main__":
    unittest.main()
