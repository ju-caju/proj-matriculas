import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.production import make_production_app
from backend.sessions import EncryptedRedisSessionStore, RedisRateLimiter


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.available = True

    def execute(self, *command):
        if not self.available:
            raise ConnectionError("redis unavailable")
        operation, key = command[:2]
        if operation == "SET":
            self.values[key] = command[2]
            self.ttls[key] = int(command[4])
            return "OK"
        if operation == "GET":
            return self.values.get(key)
        if operation == "EXPIRE":
            if key in self.values:
                self.ttls[key] = int(command[2])
                return 1
            return 0
        if operation == "DEL":
            self.ttls.pop(key, None)
            return int(self.values.pop(key, None) is not None)
        if operation == "EVAL":
            counter_key = command[3]
            count = int(self.values.get(counter_key, 0)) + 1
            self.values[counter_key] = str(count)
            self.ttls[counter_key] = int(command[4])
            return count
        raise AssertionError(command)

    def expire_key(self, key):
        self.values.pop(key, None)
        self.ttls.pop(key, None)


class SerializableSigaa:
    def __init__(self, cookies=None):
        self.cookies = cookies or []

    def login(self, username, password):
        self.cookies = [{"name": "JSESSIONID", "value": username + "-temporary-secret"}]

    def session_data(self):
        return {"cookies": self.cookies}

    @classmethod
    def from_session_data(cls, data):
        return cls(data["cookies"])

    def units(self):
        return [{"value": "2151", "label": self.cookies[0]["value"]}]


class SecureApiTest(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.sessions = EncryptedRedisSessionStore(
            self.redis,
            Fernet.generate_key().decode(),
            SerializableSigaa.from_session_data,
            token_factory=lambda: "random-session-a",
        )
        self.limiter = RedisRateLimiter(self.redis)
        self.client = TestClient(
            create_app(
                client_factory=SerializableSigaa,
                sessions=self.sessions,
                login_limiter=self.limiter,
                client_ip=lambda request: request.headers.get("X-Platform-IP"),
                secure_cookie=True,
                cookie_path="/api",
            ),
            base_url="https://127.0.0.1:8765",
        )

    def tearDown(self):
        self.client.close()

    def request(self, path, body=None, ip="203.0.113.10", cookie=True):
        headers = {
            "host": "127.0.0.1:8765",
            "origin": "http://127.0.0.1:8765",
            "Content-Type": "application/json",
        }
        if ip is not None:
            headers["x-platform-ip"] = ip
        if not cookie:
            self.client.cookies.clear()
        response = self.client.post(path, json=body or {}, headers=headers)
        return (
            response.status_code,
            response.json(),
            response.headers.get("set-cookie"),
        )

    def login(self, username="student", **kwargs):
        return self.request(
            "/api/login", {"username": username, "password": "password"}, **kwargs
        )

    def test_session_is_encrypted_isolated_renewed_and_contains_no_password(self):
        status, _, cookie = self.login()
        self.assertEqual(200, status)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Path=/api", cookie)

        stored = self.redis.values["session:random-session-a"]
        self.assertNotIn("student-temporary-secret", stored)
        self.assertNotIn("password", stored)
        self.redis.ttls["session:random-session-a"] = 1
        self.assertEqual(200, self.request("/api/units")[0])
        self.assertEqual(1800, self.redis.ttls["session:random-session-a"])

        other_sessions = EncryptedRedisSessionStore(
            self.redis,
            Fernet.generate_key().decode(),
            SerializableSigaa.from_session_data,
        )
        with self.assertRaises(ValueError):
            other_sessions.get("random-session-a")

    def test_expired_session_is_rejected_and_invalid_use_does_not_renew_ttl(self):
        self.login()
        key = "session:random-session-a"
        self.redis.ttls[key] = 12
        self.assertEqual(404, self.request("/api/unknown")[0])
        self.assertEqual(12, self.redis.ttls[key])

        self.redis.expire_key(key)
        status, body, _ = self.request("/api/units")
        self.assertEqual(401, status)
        self.assertEqual({"error": "Sua sessão expirou. Entre novamente."}, body)

    def test_two_session_identifiers_retrieve_only_their_own_state(self):
        identifiers = iter(("session-a", "session-b"))
        self.sessions.token_factory = lambda: next(identifiers)
        self.assertEqual(200, self.login(username="alice")[0])
        cookie_a = self.client.cookies.get("session")
        self.assertEqual(
            200, self.login(username="bob", cookie=False, ip="203.0.113.11")[0]
        )
        cookie_b = self.client.cookies.get("session")

        self.assertNotEqual(cookie_a, cookie_b)
        self.assertIn("session:session-a", self.redis.values)
        self.assertIn("session:session-b", self.redis.values)
        self.client.cookies.set("session", cookie_a)
        self.assertEqual(
            "alice-temporary-secret",
            self.request("/api/units")[1]["units"][0]["label"],
        )
        self.client.cookies.set("session", cookie_b)
        self.assertEqual(
            "bob-temporary-secret",
            self.request("/api/units")[1]["units"][0]["label"],
        )

    def test_logout_deletes_session_and_expires_cookie(self):
        self.login()
        status, _, cookie = self.request("/api/logout")
        self.assertEqual(200, status)
        self.assertNotIn("session:random-session-a", self.redis.values)
        self.assertIn("Max-Age=0", cookie)
        self.assertIn("Path=/api", cookie)

    def test_sixth_login_attempt_per_ip_is_rate_limited(self):
        for _ in range(5):
            self.assertEqual(200, self.login(cookie=False)[0])
        status, body, _ = self.login(cookie=False)
        self.assertEqual(429, status)
        self.assertEqual(
            {"error": "Muitas tentativas de login. Tente novamente mais tarde."}, body
        )
        self.assertEqual(900, self.redis.ttls["login:203.0.113.10"])
        self.assertEqual(200, self.login(ip="203.0.113.11", cookie=False)[0])

    def test_students_sharing_institutional_nat_share_the_same_window(self):
        for username in ("alice", "bob", "carol", "davi", "erin"):
            self.assertEqual(
                200,
                self.login(username=username, cookie=False, ip="203.0.113.10")[0],
            )
        status, _, _ = self.login(username="fran", cookie=False, ip="203.0.113.10")
        self.assertEqual(429, status)

    def test_rate_limit_can_be_verified_without_contacting_sigaa(self):
        for _ in range(5):
            status, _, _ = self.request("/api/login", {"probe": True}, cookie=False)
            self.assertEqual(400, status)

        status, body, _ = self.request("/api/login", {"probe": True}, cookie=False)

        self.assertEqual(429, status)
        self.assertEqual(
            {"error": "Muitas tentativas de login. Tente novamente mais tarde."},
            body,
        )
        self.assertFalse(any(key.startswith("session:") for key in self.redis.values))

    def test_missing_trusted_ip_and_redis_failure_fail_closed(self):
        self.assertEqual(503, self.login(ip=None)[0])
        self.assertEqual(200, self.login()[0])
        self.redis.available = False
        self.assertEqual(503, self.login()[0])
        self.assertEqual(503, self.request("/api/units")[0])

    def test_production_requires_redis_and_encryption_configuration(self):
        with self.assertRaisesRegex(ValueError, "Redis"):
            make_production_app({})

        with self.assertRaisesRegex(ValueError, "criptografia"):
            make_production_app(
                {
                    "KV_REST_API_URL": "https://redis.example",
                    "KV_REST_API_TOKEN": "token",
                }
            )

        with self.assertRaisesRegex(ValueError, "Domínio"):
            make_production_app(
                {
                    "KV_REST_API_URL": "https://redis.example",
                    "KV_REST_API_TOKEN": "token",
                    "SESSION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                    "VERCEL_URL": "https://not-a-host.example/path",
                }
            )

    def test_production_accepts_stable_project_domain(self):
        app = make_production_app(
            {
                "KV_REST_API_URL": "https://redis.invalid",
                "KV_REST_API_TOKEN": "token",
                "SESSION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                "VERCEL_URL": "proj-matriculas-random.vercel.app",
                "PUBLIC_HOST": "proj-matriculas.vercel.app",
            }
        )
        with patch(
            "backend.sessions.RedisRestClient.execute",
            side_effect=ConnectionError("redis unavailable"),
        ):
            response = TestClient(app).post(
                "/api/login",
                json={"username": "student", "password": "password"},
                headers={
                    "host": "proj-matriculas.vercel.app",
                    "origin": "https://proj-matriculas.vercel.app",
                    "x-vercel-forwarded-for": "203.0.113.10",
                },
            )

        self.assertEqual(503, response.status_code)


if __name__ == "__main__":
    unittest.main()
