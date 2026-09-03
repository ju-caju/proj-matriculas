import json
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from backend.http import SECURITY_HEADERS
from backend.production import make_production_handler


class _UnavailableHandler(BaseHTTPRequestHandler):
    body = '{"error":"Serviço temporariamente indisponível."}'.encode()

    def log_message(self, *args):
        pass

    def reply(self):
        started_at = time.monotonic()
        self.send_response(503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(self.body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in SECURITY_HEADERS:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(self.body)
        print(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "route": urlsplit(self.path).path,
                    "result": "configuration_unavailable",
                    "status": 503,
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )

    do_GET = reply
    do_POST = reply


try:
    handler = make_production_handler()
except ValueError:
    handler = _UnavailableHandler
