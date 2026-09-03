import http.client
import json
import threading
import unittest
from http.server import HTTPServer

from backend.http import make_handler
from backend.sessions import MemorySessionStore


class ControlledSigaa:
    def __init__(self, login_error=None, units_error=None, query_error=None):
        self.login_error = login_error
        self.units_error = units_error
        self.query_error = query_error
        self.login_calls = []
        self.query_calls = []

    def login(self, username, password):
        self.login_calls.append((username, password))
        if self.login_error:
            raise self.login_error

    def units(self):
        if self.units_error:
            raise self.units_error
        return [{"value": "2151", "label": "CENTRO DE INFORMÁTICA"}]

    def query(self, year, period, unit, discipline="", teacher=""):
        self.query_calls.append((year, period, unit, discipline, teacher))
        if self.query_error:
            raise self.query_error
        return {
            "rows": [{"disciplina": "CÁLCULO", "periodo": "2026.2"}],
            "units": self.units(),
        }


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.clients = []
        self.login_error = None
        self.store = MemorySessionStore(clock=lambda: self.now)

        def factory():
            client = ControlledSigaa(login_error=self.login_error)
            self.clients.append(client)
            return client

        handler = make_handler(factory, self.store)
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection(*self.server.server_address)
        headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        set_cookie = response.getheader("Set-Cookie")
        if set_cookie:
            self.cookie = set_cookie.split(";", 1)[0]
        connection.close()
        return response.status, data, set_cookie

    def login(self):
        status, body, cookie = self.request(
            "POST", "/api/login", {"username": "aluno", "password": "segredo"}
        )
        self.assertEqual((200, {"ok": True}), (status, body))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_login_session_units_query_and_logout_keep_existing_contracts(self):
        self.assertEqual(
            (200, {"authenticated": False}),
            self.request("GET", "/api/session")[:2],
        )

        self.login()
        self.assertEqual([("aluno", "segredo")], self.clients[0].login_calls)
        self.assertEqual(
            (200, {"authenticated": True}),
            self.request("GET", "/api/session")[:2],
        )
        self.assertEqual(
            (200, {"units": [{"value": "2151", "label": "CENTRO DE INFORMÁTICA"}]}),
            self.request("POST", "/api/units", {})[:2],
        )

        status, body, _ = self.request(
            "POST",
            "/api/turmas",
            {
                "year": "2026",
                "period": "2",
                "unit": "2151",
                "discipline": " cálculo ",
                "teacher": " docente ",
            },
        )
        self.assertEqual(200, status)
        self.assertEqual("CÁLCULO", body["rows"][0]["disciplina"])
        self.assertEqual(
            [("2026", "2", "2151", "cálculo", "docente")],
            self.clients[0].query_calls,
        )

        self.assertEqual((200, {"ok": True}), self.request("POST", "/api/logout", {})[:2])
        self.assertEqual(
            (200, {"authenticated": False}),
            self.request("GET", "/api/session")[:2],
        )

    def test_expired_session_returns_existing_unauthorized_response(self):
        self.login()
        self.now += 1801

        self.assertEqual(
            (401, {"error": "Entre para consultar as turmas."}),
            self.request("POST", "/api/units", {})[:2],
        )

    def test_using_session_renews_its_inactivity_period(self):
        self.login()
        self.now += 1000
        self.assertEqual(
            (200, {"authenticated": True}),
            self.request("GET", "/api/session")[:2],
        )
        self.now += 1000

        self.assertEqual(200, self.request("POST", "/api/units", {})[0])

    def test_controlled_login_failure_is_returned_as_unauthorized(self):
        self.login_error = PermissionError("Login não confirmado.")

        self.assertEqual(
            (401, {"error": "Login não confirmado."}),
            self.request(
                "POST",
                "/api/login",
                {"username": "aluno", "password": "incorreta"},
            )[:2],
        )

    def test_invalid_input_and_unknown_route_keep_existing_errors(self):
        self.login()

        self.assertEqual(
            (400, {"error": "Dados inválidos ou resposta inesperada do SIGAA."}),
            self.request("POST", "/api/turmas", {"year": "26", "period": "9"})[:2],
        )
        self.assertEqual(
            (404, {"error": "Não encontrado."}),
            self.request("POST", "/api/desconhecida", {})[:2],
        )


if __name__ == "__main__":
    unittest.main()
