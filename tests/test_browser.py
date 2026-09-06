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
            "/frontend/course-filter.js": (
                "frontend/course-filter.js",
                "text/javascript",
            ),
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
    def check_commitments(self, page, download_dir):
        def click(text):
            page.evaluate(
                f"[...document.querySelectorAll('button')].find(b=>b.textContent==={json.dumps(text)}).click()"
            )

        def fill(title, days, slots):
            page.evaluate(
                f"document.querySelector('#commitment-name').value={json.dumps(title)}"
            )
            page.evaluate(
                f"document.querySelectorAll('#commitment-blocks fieldset:last-child input').forEach(i=>i.checked=(i.name==='day'?{json.dumps(days)}:{json.dumps(slots)}).includes(i.value))"
            )

        def create(title, days, slots):
            click("Adicionar compromisso")
            fill(title, days, slots)
            click("Salvar compromisso")

        def text(selector):
            return page.evaluate(
                f"document.querySelector({json.dumps(selector)}).textContent"
            )

        def reload():
            page.command("Page.reload")
            self.assertTrue(
                page.evaluate(
                    "(async()=>{await new Promise(r=>setTimeout(r,500));for(let i=0;i<50;i++){if(document.querySelector('#query-panel')?.hidden===false)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                    True,
                )
            )

        def semester(period):
            page.evaluate(
                f"document.querySelector('[name=period]').value='{period}';document.querySelector('#query-form').requestSubmit()"
            )
            self.assertTrue(
                page.evaluate(
                    "(async()=>{for(let i=0;i<50;i++){if(!document.querySelector('#query-form button').disabled)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                    True,
                )
            )

        # A second commitment partly overlaps the course and the first commitment.
        create("Estágio", ["2"], ["M2", "M3"])
        self.assertIn("3 pares", text("#conflict-status"))
        blocks = page.evaluate(
            "[...document.querySelector('[aria-label=Segunda]').querySelectorAll('.class-block')].map(b=>{const r=b.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}})"
        )
        self.assertEqual(4, len(blocks))
        for index, a in enumerate(blocks):
            for b in blocks[index + 1 :]:
                self.assertFalse(
                    a["left"] < b["right"]
                    and b["left"] < a["right"]
                    and a["top"] < b["bottom"]
                    and b["top"] < a["bottom"]
                )

        # Export the actual download, including three simultaneous activities.
        page.command(
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
        click("Baixar imagem")
        png = Path(download_dir) / "minha-grade-ufpb-2026.2.png"
        for _ in range(100):
            if png.exists():
                break
            time.sleep(0.05)
        self.assertTrue(png.exists())
        self.assertEqual(b"\x89PNG\r\n\x1a\n", png.read_bytes()[:8])
        artifact_dir = os.environ.get("BROWSER_ARTIFACT_DIR")
        if artifact_dir:
            Path(artifact_dir).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(png, Path(artifact_dir) / "grade-conflitos.png")

        page.evaluate(
            "document.querySelector('[aria-label=\"Editar Trabalho\"]').click()"
        )
        fill("Trabalho revisado", ["5"], ["T1"])
        # Editing keeps earlier day groups, so remove them through the form.
        page.evaluate(
            "document.querySelectorAll('#commitment-blocks fieldset').forEach((g,i,all)=>{if(i<all.length-1)g.querySelector('button').click()})"
        )
        click("Salvar compromisso")
        self.assertIn("1 par", text("#conflict-status"))
        page.evaluate(
            "document.querySelector('[aria-label=\"Remover Estágio Compromisso pessoal\"]').click()"
        )
        self.assertIn("Sem choques", text("#conflict-status"))
        reload()
        self.assertIn("Trabalho revisado", text("#selected-list"))
        self.assertIn("DISCIPLINA DE TESTE", text("#selected-list"))

        semester("1")
        self.assertNotIn("Trabalho revisado", text("#selected-list"))
        create("Outro semestre", ["3"], ["N1"])
        semester("2")
        click("Limpar grade")
        self.assertEqual("", text("#selected-list"))
        reload()
        self.assertEqual("", text("#selected-list"))
        semester("1")
        self.assertIn("Outro semestre", text("#selected-list"))
        semester("2")

        # Validation, different hours per day, duplicate blocks, and touching intervals.
        click("Adicionar compromisso")
        fill("   ", ["2"], ["M2"])
        click("Salvar compromisso")
        self.assertIn("Informe um nome", text("#commitment-error"))
        fill("Rotina", [], [])
        click("Salvar compromisso")
        self.assertTrue(
            page.evaluate("document.querySelector('#commitment-dialog').open")
        )
        fill("Rotina", ["2", "4"], ["M2"])
        click("Adicionar outro horário")
        fill("Rotina", ["5"], ["T1"])
        click("Adicionar outro horário")
        fill("Rotina", ["2"], ["M2"])
        click("Salvar compromisso")
        self.assertEqual(
            3,
            page.evaluate("document.querySelectorAll('#calendar .class-block').length"),
        )
        create("Consecutivo", ["2"], ["M3"])
        self.assertIn("Sem choques", text("#conflict-status"))
        self.assertIn("Quinta", text("#selected-list"))
        self.assertIn("13:00", text("#selected-list"))
        png.unlink()
        click("Baixar imagem")
        for _ in range(100):
            if png.exists():
                break
            time.sleep(0.05)
        self.assertTrue(png.exists())
        if artifact_dir:
            shutil.copyfile(png, Path(artifact_dir) / "grade-compromissos.png")
        # Storage failure remains visible while the in-memory edit still succeeds.
        page.evaluate(
            "Storage.prototype.setItem=function(){throw new DOMException('Quota exceeded','QuotaExceededError')}"
        )
        page.evaluate(
            "document.querySelector('[aria-label=\"Editar Consecutivo\"]').click()"
        )
        fill("Consecutivo revisado", ["2"], ["M2"])
        click("Salvar compromisso")
        self.assertIn("Não foi possível salvar", text("#save-note"))
        self.assertIn("choque", text("#status"))
        self.assertIn("Consecutivo revisado", text("#selected-list"))
        # Adding a course after commitments still warns and permits inclusion.
        page.evaluate("document.querySelector('#courses article button').click()")
        self.assertIn("choque", text("#status"))
        self.assertIn("DISCIPLINA DE TESTE", text("#selected-list"))

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
                "--disable-dev-shm-usage",
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
            chrome_errors = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and browser_url is None:
                ready, _, _ = select.select([chrome.stderr], [], [], 0.2)
                if ready:
                    line = chrome.stderr.readline()
                    chrome_errors.append(line.rstrip())
                    if "DevTools listening on " in line:
                        browser_url = line.split("DevTools listening on ", 1)[1].strip()
                elif chrome.poll() is not None:
                    break
            self.assertIsNotNone(
                browser_url,
                "Chrome não abriu o protocolo DevTools:\n"
                + "\n".join(chrome_errors[-20:]),
            )
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
                "document.querySelector('#shift-filter').value='evening'; document.querySelector('#shift-filter').dispatchEvent(new Event('change'))"
            )
            self.assertEqual(
                "0 turmas disponíveis",
                devtools.evaluate("document.querySelector('#count').textContent"),
            )
            devtools.evaluate(
                "document.querySelector('#shift-filter').value='morning'; document.querySelector('#shift-filter').dispatchEvent(new Event('change'))"
            )
            self.assertEqual(
                "1 turma disponível",
                devtools.evaluate("document.querySelector('#count').textContent"),
            )
            devtools.evaluate(
                "document.querySelector('#courses article button').click()"
            )
            self.assertEqual(
                "Itens na grade (1 turma · 0 compromissos) · detalhes e remoção",
                devtools.evaluate(
                    "document.querySelector('#selected-summary').textContent"
                ),
            )
            devtools.evaluate("document.querySelector('#new-commitment').click()")
            self.assertTrue(
                devtools.evaluate("document.querySelector('#commitment-dialog').open")
            )
            devtools.evaluate(
                "document.querySelector('#commitment-name').value='Trabalho'; document.querySelector('[name=day][value=\"2\"]').checked=true; document.querySelector('[name=day][value=\"4\"]').checked=true; document.querySelector('[name=slot][value=M2]').checked=true; document.querySelector('#commitment-form').requestSubmit()"
            )
            self.assertIn(
                "Trabalho",
                devtools.evaluate(
                    "document.querySelector('#selected-list').textContent"
                ),
            )
            self.assertIn(
                "choque",
                devtools.evaluate(
                    "document.querySelector('#conflict-status').textContent"
                ),
            )
            self.assertEqual(
                4,
                devtools.evaluate(
                    "document.querySelectorAll('#calendar .class-block').length"
                ),
            )
            devtools.evaluate("document.querySelector('#export-plan').click()")
            self.assertTrue(
                devtools.evaluate(
                    "(async()=>{for(let i=0;i<50&&!document.querySelector('#status').textContent.includes('Imagem PNG');i++)await new Promise(r=>setTimeout(r,20));return document.querySelector('#status').textContent.includes('Imagem PNG')})()",
                    True,
                )
            )
            self.check_commitments(devtools, profile.name)
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
