import unittest

from fastapi.testclient import TestClient

from backend.demo import DemoSessionStore, DemoSigaa, make_demo_app


class DemoTest(unittest.TestCase):
    environment = {
        "APP_MODE": "demo",
        "VERCEL_ENV": "preview",
        "VERCEL_URL": "demo.example.vercel.app",
    }
    headers = {
        "host": "demo.example.vercel.app",
        "origin": "https://demo.example.vercel.app",
    }

    def test_fixed_login_and_filtered_synthetic_rows(self):
        client = TestClient(
            make_demo_app(self.environment),
            base_url="https://demo.example.vercel.app",
        )

        denied = client.post(
            "/api/login",
            json={"username": "real-user", "password": "real-password"},
            headers=self.headers,
        )
        self.assertEqual(401, denied.status_code)

        login = client.post(
            "/api/login",
            json={"username": "demo", "password": "demo"},
            headers=self.headers,
        )
        self.assertEqual(200, login.status_code)
        self.assertIn("Secure", login.headers["set-cookie"])

        result = client.post(
            "/api/turmas",
            json={
                "year": "2026",
                "period": "2",
                "unit": "2151",
                "discipline": "dados",
                "teacher": "daniel",
            },
            headers=self.headers,
        )
        self.assertEqual(200, result.status_code)
        self.assertEqual(
            ["BANCO DE DADOS"], [row["disciplina"] for row in result.json()["rows"]]
        )

    def test_session_does_not_depend_on_process_memory(self):
        first = DemoSessionStore()
        session_id = first.create(DemoSigaa())

        self.assertIsInstance(DemoSessionStore().get(session_id), DemoSigaa)

    def test_demo_is_refused_in_production(self):
        environment = dict(self.environment, VERCEL_ENV="production")

        with self.assertRaises(ValueError):
            make_demo_app(environment)

    def test_demo_requires_explicit_mode_and_trusted_host(self):
        for environment in (
            dict(self.environment, APP_MODE="production"),
            dict(self.environment, VERCEL_URL="https://bad.example"),
        ):
            with self.subTest(environment=environment):
                with self.assertRaises(ValueError):
                    make_demo_app(environment)


if __name__ == "__main__":
    unittest.main()
