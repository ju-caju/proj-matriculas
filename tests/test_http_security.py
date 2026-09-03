import http.client
import json
import threading
import unittest
from http.server import HTTPServer

from cryptography.fernet import Fernet

from backend.http import make_handler
from backend.production import make_production_handler, vercel_client_ip
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
        self.cookies = [{"name": "JSESSIONID", "value": "temporary-secret"}]

    def session_data(self):
        return {"cookies": self.cookies}

    @classmethod
    def from_session_data(cls, data):
        return cls(data["cookies"])

    def units(self):
        return [{"value": "2151", "label": "CI"}]


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
        handler = make_handler(
            SerializableSigaa,
            self.sessions,
            login_limiter=self.limiter,
            client_ip=lambda request: request.headers.get("X-Platform-IP"),
            secure_cookie=True,
            cookie_path="/api",
        )
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None, ip="203.0.113.10", cookie=True):
        connection = http.client.HTTPConnection(*self.server.server_address)
        headers = {
            "Host": "127.0.0.1:8765",
            "Origin": "http://127.0.0.1:8765",
            "Content-Type": "application/json",
        }
        if ip is not None:
            headers["X-Platform-IP"] = ip
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        connection.request("POST", path, json.dumps(body or {}), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read()), response.getheader("Set-Cookie")
        if result[2]:
            self.cookie = result[2].split(";", 1)[0]
        connection.close()
        return result

    def login(self, **kwargs):
        return self.request(
            "/api/login", {"username": "student", "password": "password"}, **kwargs
        )

    def test_session_is_encrypted_isolated_renewed_and_contains_no_password(self):
        status, _, cookie = self.login()
        self.assertEqual(200, status)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Path=/api", cookie)

        stored = self.redis.values["session:random-session-a"]
        self.assertNotIn("temporary-secret", stored)
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
        self.assertEqual(200, self.login()[0])
        cookie_a = self.cookie
        self.assertEqual(200, self.login(cookie=False, ip="203.0.113.11")[0])
        cookie_b = self.cookie

        self.assertNotEqual(cookie_a, cookie_b)
        self.assertIn("session:session-a", self.redis.values)
        self.assertIn("session:session-b", self.redis.values)
        self.cookie = cookie_a
        self.assertEqual(200, self.request("/api/units")[0])
        self.cookie = cookie_b
        self.assertEqual(200, self.request("/api/units")[0])

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
        self.assertEqual({"error": "Muitas tentativas de login. Tente novamente mais tarde."}, body)
        self.assertEqual(900, self.redis.ttls["login:203.0.113.10"])
        self.assertEqual(200, self.login(ip="203.0.113.11", cookie=False)[0])

    def test_missing_trusted_ip_and_redis_failure_fail_closed(self):
        self.assertEqual(503, self.login(ip=None)[0])
        self.assertEqual(200, self.login()[0])
        self.redis.available = False
        self.assertEqual(503, self.login()[0])
        self.assertEqual(503, self.request("/api/units")[0])

    def test_production_requires_redis_and_encryption_configuration(self):
        with self.assertRaisesRegex(ValueError, "Redis"):
            make_production_handler({})

        with self.assertRaisesRegex(ValueError, "criptografia"):
            make_production_handler(
                {"KV_REST_API_URL": "https://redis.example", "KV_REST_API_TOKEN": "token"}
            )


if __name__ == "__main__":
    unittest.main()
