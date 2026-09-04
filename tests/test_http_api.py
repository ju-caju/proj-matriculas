import unittest

from fastapi.testclient import TestClient

from backend.app import create_app


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
                }
            ],
            "units": self.units(),
        }


class ControlledSessionStore:
    def __init__(self):
        self.sessions = {}
        self.next_id = 1
        self.active = True

    def create(self, client):
        session_id = f"controlled-{self.next_id}"
        self.next_id += 1
        self.sessions[session_id] = client
        return session_id

    def get(self, session_id, refresh=True):
        return self.sessions.get(session_id) if self.active else None

    def refresh(self, session_id):
        return self.active and session_id in self.sessions

    def delete(self, session_id):
        self.sessions.pop(session_id, None)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.clients = []
        self.login_error = None
        self.store = ControlledSessionStore()

        def factory():
            client = ControlledSigaa(login_error=self.login_error)
            self.clients.append(client)
            return client

        self.client = TestClient(
            create_app(client_factory=factory, sessions=self.store)
        )

    def tearDown(self):
        self.client.close()

    def request(self, method, path, body=None):
        response = self.client.request(method, path, json=body)
        return response.status_code, response.json(), response.headers.get("set-cookie")

    def login(self):
        status, body, cookie = self.request(
            "POST", "/api/login", {"username": "aluno", "password": "segredo"}
        )
        self.assertEqual((200, {"ok": True}), (status, body))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_login_session_units_query_and_logout_keep_existing_contracts(self):
        self.assertEqual(
            (200, {"authenticated": False, "expired": False}),
            self.request("GET", "/api/session")[:2],
        )

        self.login()
        self.assertEqual([("aluno", "segredo")], self.clients[0].login_calls)
        self.assertEqual(
            (200, {"authenticated": True, "expired": False}),
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

        self.assertEqual(
            (200, {"ok": True}), self.request("POST", "/api/logout", {})[:2]
        )
        self.assertEqual(
            (200, {"authenticated": False, "expired": False}),
            self.request("GET", "/api/session")[:2],
        )

    def test_expired_session_returns_existing_unauthorized_response(self):
        self.login()
        self.store.active = False

        self.assertEqual(
            (401, {"error": "Sua sessão expirou. Entre novamente."}),
            self.request("POST", "/api/units", {})[:2],
        )

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

    def test_controlled_query_failures_keep_error_contracts(self):
        self.login()
        self.clients[0].units_error = PermissionError("Sua sessão expirou.")
        self.assertEqual(
            (401, {"error": "Sua sessão expirou."}),
            self.request("POST", "/api/units", {})[:2],
        )

        self.clients[0].units_error = None
        self.clients[0].query_error = ValueError("Página inesperada")
        valid_query = {"year": "2026", "period": "2", "unit": ""}
        self.assertEqual(
            (400, {"error": "Dados inválidos ou resposta inesperada do SIGAA."}),
            self.request("POST", "/api/turmas", valid_query)[:2],
        )

        self.clients[0].query_error = RuntimeError("Portal indisponível")
        self.assertEqual(
            (502, {"error": "Não foi possível consultar o SIGAA. Tente novamente."}),
            self.request("POST", "/api/turmas", valid_query)[:2],
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
