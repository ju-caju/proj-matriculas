import unittest

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.sessions import MemorySessionStore


class ControlledClient:
    def __init__(self, username="student"):
        self.username = username

    def login(self, username, password):
        self.username = username

    def units(self):
        return [{"value": "1", "label": self.username}]

    def query(self, year, period, unit, discipline="", teacher=""):
        return {"rows": [], "units": self.units()}


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

    def test_page_and_static_files_are_served_from_same_app(self):
        for path, content_type in (
            ("/", "text/html; charset=utf-8"),
            ("/app.js", "text/javascript; charset=utf-8"),
            ("/schedule.js", "text/javascript; charset=utf-8"),
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

    def test_post_contract_rejects_non_json_and_keeps_security_headers(self):
        response = self.client.post("/api/logout", content="{}")

        self.assertEqual(415, response.status_code)
        self.assertEqual({"error": "JSON necessário."}, response.json())
        self.assertEqual("DENY", response.headers["x-frame-options"])


if __name__ == "__main__":
    unittest.main()
