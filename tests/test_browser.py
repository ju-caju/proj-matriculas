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
            "/frontend/shared-plan.js": ("frontend/shared-plan.js", "text/javascript"),
            "/frontend/share-ui.js": ("frontend/share-ui.js", "text/javascript"),
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
    def check_sharing(self, page):
        def run(script):
            return page.evaluate(script, True)

        def click(selector):
            run(f"document.querySelector({json.dumps(selector)}).click()")

        def text(selector):
            return run(f"document.querySelector({json.dumps(selector)}).textContent")

        def wait(expression):
            self.assertTrue(
                run(
                    "(async()=>{for(let i=0;i<100;i++){if("
                    + expression
                    + ")return true;await new Promise(r=>setTimeout(r,30));}return false})()"
                ),
                run("document.body.innerText"),
            )

        def capture(name):
            directory = os.environ.get("BROWSER_ARTIFACT_DIR")
            if not directory:
                return
            Path(directory).mkdir(parents=True, exist_ok=True)
            for width, height in [(1280, 900), (390, 844)]:
                page.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                shot = page.command("Page.captureScreenshot", {"format": "png"})
                (Path(directory) / f"{name}-{width}.png").write_bytes(
                    base64.b64decode(shot["data"])
                )
            page.command("Emulation.clearDeviceMetricsOverride")

        original = run("JSON.stringify({...localStorage})")
        click("#new-commitment")
        run(
            "document.querySelector('#commitment-name').value='Reunião';document.querySelector('[name=day][value=\"2\"]').checked=true;document.querySelector('[name=slot][value=M3]').checked=true;document.querySelector('#commitment-form').requestSubmit()"
        )
        author_id = run(
            "PlanStore.createPlanStore({key:Schedule.key}).load('2026.2').find(item=>item.nome==='Reunião').id"
        )
        run(
            "Object.defineProperty(navigator,'share',{configurable:true,value:undefined})"
        )
        click("#share-plan")
        self.assertTrue(run("document.querySelector('#native-share').hidden"))
        self.assertFalse(run("document.querySelector('#share-commitments').checked"))
        self.assertEqual(
            "Fechar janela de compartilhamento",
            run("document.querySelector('#close-share').getAttribute('aria-label')"),
        )
        self.assertTrue(
            run(
                "(()=>{const button=document.querySelector('#close-share').getBoundingClientRect();const dialog=document.querySelector('#share-dialog').getBoundingClientRect();return button.right<=dialog.right&&button.top<dialog.top+70})()"
            )
        )
        self.assertIn("1 turma · 0 compromissos", text("#share-count"))
        click("#generate-share")
        course_link = run("document.querySelector('#share-link').value")
        self.assertIn("#grade=", course_link)
        self.assertEqual(
            1,
            run(
                "SharedPlan.decode(new URL(document.querySelector('#share-link').value).hash).items.length"
            ),
        )
        click("#share-commitments")
        self.assertEqual("", run("document.querySelector('#share-link').value"))
        self.assertIn("1 turma · 2 compromissos", text("#share-count"))
        click("#generate-share")
        link = run("document.querySelector('#share-link').value")
        capture("compartilhar")
        run(
            "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('denied')}}})"
        )
        click("#copy-share-link")
        wait("document.querySelector('#share-error').textContent.includes('Copie')")
        self.assertEqual(link, run("document.querySelector('#share-link').value"))
        run(
            "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.copiedLink=value}}})"
        )
        click("#copy-share-link")
        wait("document.querySelector('#share-error').textContent==='Link copiado.'")
        self.assertEqual(link, run("window.copiedLink"))
        run(
            "Object.defineProperty(navigator,'share',{configurable:true,value:async data=>{window.sharedWithSystem=data.url}})"
        )
        click("#close-share")
        click("#share-plan")
        click("#share-commitments")
        click("#generate-share")
        self.assertFalse(run("document.querySelector('#native-share').hidden"))
        click("#native-share")
        wait("window.sharedWithSystem===document.querySelector('#share-link').value")
        run(
            "Object.defineProperty(navigator,'share',{configurable:true,value:async()=>{throw Error('unavailable')}})"
        )
        click("#native-share")
        wait(
            "document.querySelector('#share-error').textContent.includes('Use Copiar link')"
        )
        click("#close-share")

        # Keep an existing duplicate and a new conflicting local item in the
        # destination period; leave a different period selected before opening.
        run(
            "PlanStore.createPlanStore({key:Schedule.key}).save('2026.2',[{type:'commitment',id:'local-work',nome:'  TRABALHO ',periodo:'2026.2',horario:'4M2 2M2'},{type:'commitment',id:'local-new',nome:'Atividade local',periodo:'2026.2',horario:'2M3'}])"
        )
        run(
            "document.querySelector('[name=period]').value='1';document.querySelector('#query-form').requestSubmit()"
        )
        wait("!document.querySelector('#query-form button').disabled")
        click("#logout")
        wait("!document.querySelector('#login-panel').hidden")
        before = run("JSON.stringify({...localStorage})")
        page.command("Network.enable")
        page.events.clear()
        run(f"location.hash=new URL({json.dumps(link)}).hash")
        wait("document.querySelector('#shared-view')?.hidden===false")
        page.command("Page.reload")
        time.sleep(0.5)
        wait("document.querySelector('#shared-view')?.hidden===false")
        self.assertIn("2026.2", text("#plan-title"))
        self.assertIn("fotografia", text("#shared-view"))
        self.assertIn("SIGAA", text("#shared-view"))
        self.assertIn("Trabalho", text("#selected-list"))
        self.assertIn("Presencial", text("#selected-list"))
        self.assertIn("REGULAR", text("#selected-list"))
        self.assertNotIn("10 vagas", text("#selected-list"))
        self.assertIn("choque", text("#conflict-status"))
        capture("grade-publica")
        self.assertEqual(before, run("JSON.stringify({...localStorage})"))
        self.assertEqual(
            0, run("document.querySelectorAll('#selected-list button').length")
        )
        self.assertFalse(
            run("document.querySelector('#calendar .class-block').draggable")
        )
        requests = [
            event["params"]["request"]
            for event in page.events
            if event["method"] == "Network.requestWillBeSent"
        ]
        self.assertFalse(
            any("/api/units" in r["url"] or "/api/turmas" in r["url"] for r in requests)
        )
        self.assertFalse(any("grade=" in r.get("postData", "") for r in requests))
        self.assertFalse(any("#" in r["url"] for r in requests if "/api/" in r["url"]))

        # Starting independently neither imports items nor requires login.
        click("#shared-home")
        wait("!location.hash && !document.querySelector('#login-panel').hidden")
        self.assertEqual(before, run("JSON.stringify({...localStorage})"))
        run(f"location.hash=new URL({json.dumps(link)}).hash")
        wait("!document.querySelector('#shared-view').hidden")

        click("#copy-shared")
        wait("!document.querySelector('#login-panel').hidden")
        self.assertEqual(
            new_hash := urllib.parse.urlparse(link).fragment,
            run("location.hash.slice(1)"),
        )
        run(
            "document.querySelector('[name=username]').value='fake-user';document.querySelector('[name=password]').value='fake-password';document.querySelector('#login-form').requestSubmit()"
        )
        wait("document.querySelector('#merge-dialog').open")
        self.assertEqual(new_hash, run("location.hash.slice(1)"))
        self.assertEqual(before, run("JSON.stringify({...localStorage})"))
        self.assertIn("1 turma · 1 compromisso", text("#merge-additions"))
        self.assertIn("0 turmas · 1 compromisso", text("#merge-duplicates"))
        self.assertIn("choque", text("#merge-conflicts"))
        capture("previa-copia")
        click("#cancel-merge")
        self.assertEqual(before, run("JSON.stringify({...localStorage})"))
        click("#copy-shared")
        wait("document.querySelector('#merge-dialog').open")
        # Session loss between preview and confirmation must return to login.
        run("document.cookie='session=; Path=/; Max-Age=0'")
        click("#confirm-merge")
        wait("!document.querySelector('#login-panel').hidden")
        self.assertEqual(before, run("JSON.stringify({...localStorage})"))
        run(
            "document.querySelector('[name=password]').value='fake-password';document.querySelector('#login-form').requestSubmit()"
        )
        wait("document.querySelector('#merge-dialog').open")
        run(
            "window.originalSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('quota')}"
        )
        click("#confirm-merge")
        wait(
            "document.querySelector('#merge-error').textContent.includes('Não foi possível salvar')"
        )
        self.assertEqual(before, run("JSON.stringify({...localStorage})"))
        self.assertTrue(run("document.querySelector('#merge-dialog').open"))
        run("Storage.prototype.setItem=window.originalSetItem")
        click("#confirm-merge")
        wait("!document.querySelector('#merge-dialog').open")
        self.assertIn("2026.2", text("#plan-title"))
        self.assertIn("Atividade local", text("#selected-list"))
        self.assertIn("DISCIPLINA DE TESTE", text("#selected-list"))
        self.assertIn("ignorado", text("#status"))
        self.assertEqual(
            4,
            run("PlanStore.createPlanStore({key:Schedule.key}).load('2026.2').length"),
        )
        self.assertNotEqual(
            author_id,
            run(
                "PlanStore.createPlanStore({key:Schedule.key}).load('2026.2').find(item=>item.nome==='Reunião').id"
            ),
        )
        run(f"location.hash=new URL({json.dumps(link)}).hash")
        wait("!document.querySelector('#shared-view').hidden")
        click("#copy-shared")
        wait("document.querySelector('#merge-dialog').open")
        self.assertIn("0 turmas · 0 compromissos", text("#merge-additions"))
        click("#confirm-merge")
        wait("!document.querySelector('#merge-dialog').open")
        self.assertEqual(
            4,
            run("PlanStore.createPlanStore({key:Schedule.key}).load('2026.2').length"),
        )

        click('[aria-label="Editar Reunião"]')
        run(
            "document.querySelector('#commitment-name').value='Reunião revisada';document.querySelector('#commitment-form').requestSubmit()"
        )
        click("#share-plan")
        click("#share-commitments")
        click("#generate-share")
        self.assertIn(
            "Reunião revisada",
            run(
                "SharedPlan.decode(new URL(document.querySelector('#share-link').value).hash).items.map(item=>item.nome).join(' ')"
            ),
        )
        click("#close-share")
        click('[aria-label="Remover Reunião revisada Compromisso pessoal"]')
        self.assertNotIn("Reunião", text("#selected-list"))

        run("location.hash='#grade=invalid'")
        wait("!document.querySelector('#shared-error').hidden")
        self.assertEqual("", text("#selected-list"))
        click("#shared-error-home")
        wait("!location.hash")
        # Untrusted text is displayed literally, even when it resembles HTML.
        run(
            "location.hash=SharedPlan.encode('2026.2',[{type:'commitment',nome:'<img src=x onerror=alert(1)>',periodo:'2026.2',horario:'2M2'}],true)"
        )
        wait("!document.querySelector('#shared-view').hidden")
        self.assertIn("<img src=x onerror=alert(1)>", text("#selected-list"))
        self.assertEqual(0, run("document.querySelectorAll('#shared-view img').length"))
        click("#shared-home")
        # A grade consisting only of commitments requires explicit inclusion.
        run(
            "PlanStore.createPlanStore({key:Schedule.key}).save('2026.2',[{type:'commitment',id:'only',nome:'Só compromisso',periodo:'2026.2',horario:'2M2'}])"
        )
        page.command("Page.reload")
        time.sleep(0.5)
        wait("!document.querySelector('#query-panel').hidden")
        click("#share-plan")
        click("#generate-share")
        self.assertIn("Inclua compromissos", text("#share-error"))
        self.assertTrue(run("document.querySelector('#share-result').hidden"))
        click("#share-commitments")
        click("#generate-share")
        self.assertIn("#grade=", run("document.querySelector('#share-link').value"))
        click("#close-share")
        click("#clear-plan")
        self.assertTrue(run("document.querySelector('#share-plan').disabled"))
        # Restore the author plan for the existing commitment/edit/export flow.
        run(
            f"localStorage.clear();Object.entries(JSON.parse({json.dumps(original)})).forEach(([key,value])=>localStorage.setItem(key,value))"
        )
        page.command("Page.reload")
        time.sleep(0.5)
        wait("!document.querySelector('#query-panel').hidden")
        run("document.querySelector('#query-form').requestSubmit()")
        wait("!!document.querySelector('#courses article')")

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

    def check_undo(self, page):
        def run(script, await_promise=False):
            return page.evaluate(script, await_promise)

        def text(selector):
            return run(f"document.querySelector({json.dumps(selector)}).textContent")

        def fail_storage(action):
            run(
                "(()=>{const originalSet=Storage.prototype.setItem;"
                "Storage.prototype.setItem=function(){throw new DOMException('Quota exceeded','QuotaExceededError')};"
                f"{action};Storage.prototype.setItem=originalSet}})()"
            )

        def wait_for_query():
            self.assertTrue(
                run(
                    "(async()=>{for(let i=0;i<50;i++){if(!document.querySelector('#query-form button').disabled)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                    True,
                )
            )

        original = run("localStorage.getItem('ufpb-plan:2026.2')")
        run("document.querySelector('#courses article button').click()")
        self.assertIn("Turma DISCIPLINA DE TESTE removida", text("#status"))
        self.assertEqual("Desfazer", text("#undo-plan"))
        self.assertEqual("BUTTON", run("document.querySelector('#undo-plan').tagName"))
        self.assertEqual(
            "status", run("document.querySelector('#status').getAttribute('role')")
        )
        self.assertEqual(
            "polite", run("document.querySelector('#status').getAttribute('aria-live')")
        )
        self.assertEqual("undo-plan", run("document.activeElement.id"))
        run("document.querySelector('#undo-plan').click()")
        self.assertIn("DISCIPLINA DE TESTE", text("#selected-list"))
        self.assertEqual(original, run("localStorage.getItem('ufpb-plan:2026.2')"))
        self.assertEqual("status", run("document.activeElement.id"))
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))

        run(
            "document.querySelector('[aria-label=\"Remover DISCIPLINA DE TESTE 01\"]').click()"
        )
        self.assertNotIn("DISCIPLINA DE TESTE", text("#selected-list"))
        run("document.querySelector('#undo-plan').click()")

        run(
            "document.querySelector('[aria-label=\"Remover Trabalho Compromisso pessoal\"]').click()"
        )
        self.assertIn("Compromisso Trabalho removido", text("#status"))
        run("document.querySelector('#undo-plan').click()")
        self.assertIn("Trabalho", text("#selected-list"))
        self.assertEqual(original, run("localStorage.getItem('ufpb-plan:2026.2')"))

        run("document.querySelector('#clear-plan').click()")
        self.assertIn("Grade limpa", text("#status"))
        self.assertEqual("undo-plan", run("document.activeElement.id"))
        run("document.querySelector('#undo-plan').click()")
        self.assertEqual(original, run("localStorage.getItem('ufpb-plan:2026.2')"))
        self.assertIn("1 turma · 1 compromisso", text("#selected-summary"))
        self.assertIn("choque", text("#conflict-status"))

        fail_storage("document.querySelector('#clear-plan').click()")
        self.assertIn("1 turma · 1 compromisso", text("#selected-summary"))
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))

        run("document.querySelector('#filter').focus()")
        run(
            "(()=>{const data=new DataTransfer(),block=document.querySelector('#calendar .class-block');"
            "block.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:data}));"
            "document.body.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:data}))})()"
        )
        self.assertEqual("filter", run("document.activeElement.id"))
        self.assertNotIn("DISCIPLINA DE TESTE", text("#selected-list"))
        self.assertNotEqual(original, run("localStorage.getItem('ufpb-plan:2026.2')"))
        self.assertFalse(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#undo-plan').click()")
        self.assertEqual(original, run("localStorage.getItem('ufpb-plan:2026.2')"))

        fail_storage("document.querySelector('#courses article button').click()")
        self.assertIn("DISCIPLINA DE TESTE", text("#selected-list"))
        self.assertIn("Não foi possível salvar", text("#status"))
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))

        run("document.querySelector('#courses article button').click()")
        fail_storage("document.querySelector('#undo-plan').click()")
        self.assertNotIn("DISCIPLINA DE TESTE", text("#selected-list"))
        self.assertFalse(run("document.querySelector('#undo-plan').hidden"))
        self.assertIn("Não foi possível salvar", text("#status"))
        run("document.querySelector('#undo-plan').click()")
        self.assertIn("DISCIPLINA DE TESTE", text("#selected-list"))

        run("document.querySelector('#courses article button').click()")
        run(
            "document.querySelector('#filter').value='teste';document.querySelector('#filter').dispatchEvent(new Event('input'))"
        )
        self.assertFalse(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#query-form').requestSubmit()")
        wait_for_query()
        self.assertFalse(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#export-plan').click()")
        self.assertTrue(
            run(
                "(async()=>{for(let i=0;i<50;i++){if(document.querySelector('#status-message').textContent.includes('Imagem PNG'))return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                True,
            )
        )
        self.assertFalse(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#courses article button').click()")
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))

        run("document.querySelector('#courses article button').click()")
        run(
            "localStorage.setItem('ufpb-plan:2026.2',JSON.stringify(["
            "{type:'commitment',id:'other-tab',nome:'Outra aba',periodo:'2026.2',horario:'3N1'}]));"
            "document.querySelector('#undo-plan').click()"
        )
        self.assertIn("Outra aba", text("#selected-list"))
        self.assertNotIn("DISCIPLINA DE TESTE", text("#selected-list"))
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))

        run(f"localStorage.setItem('ufpb-plan:2026.2',{json.dumps(original)})")
        page.command("Page.reload")
        time.sleep(0.5)
        self.assertTrue(
            run(
                "(async()=>{for(let i=0;i<50;i++){if(document.querySelector('#query-panel')?.hidden===false)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                True,
            )
        )
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#query-form').requestSubmit()")
        wait_for_query()

        run("document.querySelector('#courses article button').click()")
        run(
            "document.querySelector('[name=period]').value='1';document.querySelector('#query-form').requestSubmit()"
        )
        wait_for_query()
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))
        run(
            "document.querySelector('[name=period]').value='2';document.querySelector('#query-form').requestSubmit()"
        )
        wait_for_query()

        run(f"localStorage.setItem('ufpb-plan:2026.2',{json.dumps(original)})")
        page.command("Page.reload")
        time.sleep(0.5)
        run("document.querySelector('#query-form').requestSubmit()")
        wait_for_query()
        run("document.querySelector('#courses article button').click()")
        run("location.hash=SharedPlan.encode('2026.2',[" + json.dumps(FAKE_ROW) + "])")
        self.assertTrue(
            run(
                "(async()=>{for(let i=0;i<50;i++){if(!document.querySelector('#shared-view').hidden)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                True,
            )
        )
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#shared-home').click()")

        run(f"localStorage.setItem('ufpb-plan:2026.2',{json.dumps(original)})")
        run("document.querySelector('#courses article button').click()")
        run("document.querySelector('#courses article button').click()")
        self.assertFalse(run("document.querySelector('#undo-plan').hidden"))
        run("document.querySelector('#logout').click()")
        self.assertTrue(
            run(
                "(async()=>{for(let i=0;i<50;i++){if(!document.querySelector('#login-panel').hidden)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                True,
            )
        )
        self.assertTrue(run("document.querySelector('#undo-plan').hidden"))
        run(f"localStorage.setItem('ufpb-plan:2026.2',{json.dumps(original)})")
        run(
            "document.querySelector('[name=username]').value='fake-user';document.querySelector('[name=password]').value='fake-password';document.querySelector('#login-form').requestSubmit()"
        )
        self.assertTrue(
            run(
                "(async()=>{for(let i=0;i<50;i++){if(!document.querySelector('#query-panel').hidden)return true;await new Promise(r=>setTimeout(r,50));}return false})()",
                True,
            )
        )
        run("document.querySelector('#query-form').requestSubmit()")
        wait_for_query()

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
            self.check_undo(devtools)
            devtools.evaluate("document.querySelector('#export-plan').click()")
            self.assertTrue(
                devtools.evaluate(
                    "(async()=>{for(let i=0;i<50&&!document.querySelector('#status').textContent.includes('Imagem PNG');i++)await new Promise(r=>setTimeout(r,20));return document.querySelector('#status').textContent.includes('Imagem PNG')})()",
                    True,
                )
            )
            self.check_sharing(devtools)
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
