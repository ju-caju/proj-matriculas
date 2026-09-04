import io
import json
import logging
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request

from backend.sigaa import (
    AllowlistRedirectHandler,
    SigaaResponseTooLarge,
    UrllibTransport,
)


class _Socket:
    def __init__(self):
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value


class _Response:
    def __init__(self, body):
        self.url = "https://sigaa.ufpb.br/sigaa/logon.jsf"
        self.headers = Message()
        self.fp = type("File", (), {"raw": type("Raw", (), {"_sock": _Socket()})()})()
        self.body = body
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        self.read_sizes.append(size)
        result, self.body = self.body[:size], self.body[size:]
        return result


class _Opener:
    def __init__(self, response):
        self.response = response
        self.timeout = None

    def open(self, request, timeout):
        self.timeout = timeout
        return self.response


class SigaaBoundaryTest(unittest.TestCase):
    def test_transport_has_separate_deadlines_and_rejects_oversized_body(self):
        response = _Response(b"12345")
        opener = _Opener(response)
        with patch("backend.sigaa.build_opener", return_value=opener):
            transport = UrllibTransport(
                connect_timeout=3, read_timeout=7, max_response_bytes=4
            )
            with self.assertRaises(SigaaResponseTooLarge):
                transport.request("/sigaa/logon.jsf")

        self.assertEqual(3, opener.timeout)
        self.assertEqual(7, response.fp.raw._sock.timeout)
        self.assertEqual([5], response.read_sizes)

    def test_redirect_handler_rejects_hosts_outside_allowlist(self):
        handler = AllowlistRedirectHandler(("sigaa.ufpb.br",))
        request = Request("https://sigaa.ufpb.br/sigaa/logon.jsf")
        with self.assertRaises(URLError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://phishing.example/login",
            )

        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://sigaa.ufpb.br/sigaa/portais/discente/discente.jsf",
        )
        self.assertEqual(
            "https://sigaa.ufpb.br/sigaa/portais/discente/discente.jsf",
            redirected.full_url,
        )


class StructuredLogTest(unittest.TestCase):
    def test_logs_are_allowlisted_and_do_not_include_request_data(self):
        from fastapi.testclient import TestClient

        from backend.app import create_app

        class Client:
            def login(self, username, password):
                pass

            def units(self):
                return []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("matriculas.http")
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            client = TestClient(create_app(client_factory=Client))
            client.post(
                "/api/login",
                json={
                    "username": "student-secret",
                    "password": "password-secret",
                    "filter": "CÁLCULO ACADÊMICO",
                    "html": "<table>PRIVATE</table>",
                },
            )
            client.get("/unknown/password-secret?filter=PRIVATE")
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

        lines = [line for line in stream.getvalue().splitlines() if line]
        self.assertGreaterEqual(len(lines), 2)
        for line in lines:
            payload = json.loads(line)
            self.assertEqual(
                {"event", "route", "status", "result", "duration_ms"},
                set(payload),
            )
            self.assertNotIn("student-secret", line)
            self.assertNotIn("password-secret", line)
            self.assertNotIn("PRIVATE", line)
            self.assertNotIn("CÁLCULO", line)


if __name__ == "__main__":
    unittest.main()
