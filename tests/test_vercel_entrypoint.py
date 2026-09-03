import http.client
import importlib.util
import json
import os
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch


ENTRYPOINT = Path(__file__).parent.parent / "api" / "index.py"
API_ROOT = ENTRYPOINT.parent
VERCEL_CONFIG = Path(__file__).parent.parent / "vercel.json"


class VercelEntrypointTest(unittest.TestCase):
    def test_each_api_route_defines_its_own_named_handler(self):
        for path in API_ROOT.glob("*.py"):
            module_name = "vercel_" + path.stem
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            with patch.dict(os.environ, {}, clear=True):
                spec.loader.exec_module(module)

            self.assertEqual("handler", module.handler.__name__, path.name)
            self.assertEqual(module_name, module.handler.__module__, path.name)

    def test_function_pattern_matches_python_entrypoints_in_api_root(self):
        config = json.loads(VERCEL_CONFIG.read_text())

        self.assertIn("api/*.py", config["functions"])

    def test_missing_configuration_fails_closed_with_generic_response(self):
        spec = importlib.util.spec_from_file_location("vercel_entrypoint", ENTRYPOINT)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {}, clear=True):
            spec.loader.exec_module(module)

        self.assertEqual("handler", module.handler.__name__)
        server = HTTPServer(("127.0.0.1", 0), module.handler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(*server.server_address)
        connection.request("GET", "/api/session")
        response = connection.getresponse()
        body = response.read()
        connection.close()
        thread.join()
        server.server_close()

        self.assertEqual(503, response.status)
        self.assertEqual(
            '{"error":"Serviço temporariamente indisponível."}'.encode(), body
        )
        self.assertEqual("nosniff", response.getheader("X-Content-Type-Options"))
        self.assertEqual("DENY", response.getheader("X-Frame-Options"))
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))


if __name__ == "__main__":
    unittest.main()
