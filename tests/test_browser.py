"""Smoke-test the complete frontend flow in a real browser.

The API below is deliberately synthetic.  It never contacts SIGAA and does not
contain a real student's credentials or academic data.
"""

import base64
import http.server
import json
import os
import select
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAKE_ROW = {
    "disciplina": "DISCIPLINA DE TESTE",
    "periodo": "2026.2",
    "turma": "01",
    "docente": "DOCENTE DE TESTE",
    "tipo": "REGULAR",
    "forma": "Presencial",
    "situacao": "ABERTA",
    "horario": "24M23",
    "local": "SALA DE TESTE",
    "vagas": "10 vagas",
}


class FakeBackend(http.server.BaseHTTPRequestHandler):
    rows = [FAKE_ROW]

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler API
        return

    def _json(self, status, value, cookie=None):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/api/session":
            authenticated = "session=fake" in self.headers.get("Cookie", "")
            return self._json(200, {"authenticated": authenticated, "expired": False})
        files = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/schedule.js": ("schedule.js", "text/javascript"),
            "/frontend/dom.js": ("frontend/dom.js", "text/javascript"),
            "/frontend/plan-store.js": ("frontend/plan-store.js", "text/javascript"),
            "/frontend/api-client.js": ("frontend/api-client.js", "text/javascript"),
            "/frontend/grade-image.js": ("frontend/grade-image.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if self.path not in files:
            self.send_error(404)
            return
        filename, media_type = files[self.path]
        with open(ROOT / filename, "rb") as source:
            body = source.read()
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        authenticated = "session=fake" in self.headers.get("Cookie", "")
        if self.path == "/api/login":
            return self._json(
                200, {"ok": True}, "session=fake; Path=/; SameSite=Strict"
            )
        if self.path == "/api/logout":
            return self._json(200, {"ok": True}, "session=; Path=/; Max-Age=0")
        if not authenticated:
            return self._json(401, {"error": "Sessão expirada."})
        if self.path == "/api/units":
            return self._json(
                200, {"units": [{"value": "2151", "label": "Unidade de teste"}]}
            )
        if self.path == "/api/turmas":
            return self._json(
                200,
                {
                    "rows": self.rows,
                    "units": [{"value": "2151", "label": "Unidade de teste"}],
                },
            )
        return self._json(404, {"error": "Não encontrado."})


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class DevTools:
    """Tiny websocket client for the Chrome DevTools Protocol (stdlib only)."""

    def __init__(self, websocket_url):
        parsed = urllib.parse.urlparse(websocket_url)
        self.socket = socket.create_connection(
            (parsed.hostname, parsed.port), timeout=10
        )
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.netloc}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
        self.socket.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError("Chrome DevTools websocket handshake failed")
        self.sequence = 0
        self.events = []

    def _frame(self, payload, opcode=1):
        value = bytes(payload)
        length = len(value)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + length.to_bytes(2, "big")
        else:
            header += bytes([0x80 | 127]) + length.to_bytes(8, "big")
        mask = os.urandom(4)
        return (
            header
            + mask
            + bytes(item ^ mask[index % 4] for index, item in enumerate(value))
        )

    def _read(self):
        header = self.socket.recv(2)
        if not header:
            raise RuntimeError("Chrome closed DevTools websocket")
        length = header[1] & 0x7F
        if length == 126:
            length = int.from_bytes(self.socket.recv(2), "big")
        elif length == 127:
            length = int.from_bytes(self.socket.recv(8), "big")
        masked = header[1] & 0x80
        mask = self.socket.recv(4) if masked else b""
        payload = bytearray()
        while len(payload) < length:
            payload += self.socket.recv(length - len(payload))
        if masked:
            payload = bytearray(
                item ^ mask[index % 4] for index, item in enumerate(payload)
            )
        if header[0] & 0x0F == 9:
            self.socket.sendall(self._frame(payload, 10))
            return self._read()
        return json.loads(payload)

    def command(self, method, params=None, await_promise=False):
        self.sequence += 1
        identifier = self.sequence
        message = {"id": identifier, "method": method}
        if params:
            message["params"] = params
        self.socket.sendall(self._frame(json.dumps(message).encode()))
        while True:
            response = self._read()
            if response.get("id") == identifier:
                if "exceptionDetails" in response.get("result", {}):
                    raise AssertionError(response["result"]["exceptionDetails"])
                return response.get("result", {})
            self.events.append(response)

    def evaluate(self, expression, await_promise=False):
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        remote = result.get("result", {})
        if remote.get("type") == "undefined":
            return None
        return remote.get("value")

    def close(self):
        self.socket.close()


@unittest.skipUnless(shutil.which("google-chrome"), "Google Chrome não está instalado")
class BrowserFlowTest(unittest.TestCase):
    def test_login_query_plan_and_logout_with_fake_backend(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBackend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        profile = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        chrome = subprocess.Popen(
            [
                "google-chrome",
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--remote-debugging-port=0",
                "--user-data-dir=" + profile.name,
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        devtools = None
        try:
            browser_url = None
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and browser_url is None:
                ready, _, _ = select.select([chrome.stderr], [], [], 0.2)
                if ready:
                    line = chrome.stderr.readline()
                    if "DevTools listening on " in line:
                        browser_url = line.split("DevTools listening on ", 1)[1].strip()
            self.assertIsNotNone(browser_url, "Chrome não abriu o protocolo DevTools")
            browser = urllib.parse.urlparse(browser_url)
            with urllib.request.urlopen(
                f"http://{browser.netloc}/json/list", timeout=5
            ) as response:
                targets = json.load(response)
            page = next(target for target in targets if target.get("type") == "page")
            devtools = DevTools(page["webSocketDebuggerUrl"])
            devtools.command("Page.enable")
            devtools.command("Runtime.enable")
            devtools.command(
                "Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/"}
            )
            for _ in range(50):
                if devtools.evaluate("document.readyState") == "complete":
                    break
                time.sleep(0.1)
            time.sleep(0.5)
            self.assertEqual(
                ["object", "object", "object", "object"],
                devtools.evaluate(
                    "[typeof Schedule,typeof FrontendDom,typeof PlanStore,typeof ApiClient]"
                ),
                devtools.evaluate("location.href"),
            )

            self.assertTrue(
                devtools.evaluate("!document.querySelector('#login-panel').hidden")
            )
            self.assertFalse(
                devtools.evaluate(
                    "document.querySelector('#login-form').dispatchEvent(new Event('submit',{cancelable:true}))"
                ),
                repr(devtools.events),
            )
            devtools.evaluate(
                "document.querySelector('[name=username]').value='fake-user'; document.querySelector('[name=password]').value='fake-password'; document.querySelector('#login-form').requestSubmit()"
            )
            logged_in = devtools.evaluate(
                "(async()=>{for(let i=0;i<50&&document.querySelector('#query-panel')?.hidden;i++)await new Promise(r=>setTimeout(r,20));return document.querySelector('#query-panel')?.hidden===false})()",
                True,
            )
            self.assertTrue(
                logged_in,
                devtools.evaluate(
                    "location.href + '\\n' + document.body.innerText + '\\n' + typeof FrontendDom + ' ' + typeof PlanStore + ' ' + typeof ApiClient + ' ' + typeof GradeImage"
                )
                + "\\n"
                + repr(devtools.events[-10:]),
            )
            self.assertEqual(
                "Unidade de teste",
                devtools.evaluate(
                    "document.querySelector('[name=unit] option[value=\"2151\"]').textContent"
                ),
            )
            devtools.evaluate(
                "document.querySelector('[name=year]').value='2026'; document.querySelector('[name=period]').value='2'; document.querySelector('#query-form').requestSubmit()"
            )
            self.assertTrue(
                devtools.evaluate(
                    "(async()=>{for(let i=0;i<50&&!document.querySelector('#courses article');i++)await new Promise(r=>setTimeout(r,20));return !!document.querySelector('#courses article')})()",
                    True,
                )
            )
            devtools.evaluate(
                "document.querySelector('#courses article button').click()"
            )
            self.assertEqual(
                "Turmas na grade (1) · detalhes e remoção",
                devtools.evaluate(
                    "document.querySelector('#selected-summary').textContent"
                ),
            )
            devtools.evaluate("document.querySelector('#export-plan').click()")
            self.assertTrue(
                devtools.evaluate(
                    "(async()=>{for(let i=0;i<50&&!document.querySelector('#status').textContent.includes('Imagem PNG');i++)await new Promise(r=>setTimeout(r,20));return document.querySelector('#status').textContent.includes('Imagem PNG')})()",
                    True,
                )
            )
            devtools.evaluate("document.querySelector('#logout').click()")
            time.sleep(0.5)
            logged_out = devtools.evaluate(
                "(async()=>{for(let i=0;i<50&&document.querySelector('#login-panel')?.hidden===false;i++)await new Promise(r=>setTimeout(r,20));return document.querySelector('#login-panel')?.hidden===false})()",
                True,
            )
            self.assertTrue(
                logged_out,
                devtools.evaluate("document.body.innerText")
                + "\\n"
                + repr(devtools.events[-5:]),
            )
        finally:
            if devtools:
                devtools.close()
            chrome.terminate()
            try:
                chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome.kill()
                chrome.wait(timeout=5)
            if chrome.stderr:
                chrome.stderr.close()
            profile.cleanup()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
