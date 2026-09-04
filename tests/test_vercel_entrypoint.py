import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ENTRYPOINT = Path(__file__).parent.parent / "api" / "index.py"
API_ROOT = ENTRYPOINT.parent
VERCEL_CONFIG = Path(__file__).parent.parent / "vercel.json"


class VercelEntrypointTest(unittest.TestCase):
    def test_index_is_the_only_vercel_entrypoint_and_exports_fastapi(self):
        self.assertEqual([ENTRYPOINT], list(API_ROOT.glob("*.py")))
        spec = importlib.util.spec_from_file_location("vercel_entrypoint", ENTRYPOINT)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {}, clear=True):
            spec.loader.exec_module(module)

        self.assertIsInstance(module.app, FastAPI)

    def test_vercel_routes_all_paths_to_the_fastapi_entrypoint(self):
        config = json.loads(VERCEL_CONFIG.read_text())

        self.assertEqual({"api/index.py"}, set(config["functions"]))
        self.assertEqual(
            [{"source": "/(.*)", "destination": "/api/index.py"}],
            config["rewrites"],
        )

    def test_vercel_git_integration_keeps_preview_deployments_enabled(self):
        config = json.loads(VERCEL_CONFIG.read_text())

        self.assertTrue(config["git"]["deploymentEnabled"])

    def test_missing_configuration_fails_closed_with_generic_response(self):
        spec = importlib.util.spec_from_file_location("vercel_entrypoint", ENTRYPOINT)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {}, clear=True):
            spec.loader.exec_module(module)

        response = TestClient(module.app).get("/api/session")

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            {"error": "Serviço temporariamente indisponível."}, response.json()
        )
        self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
        self.assertEqual("DENY", response.headers["X-Frame-Options"])
        self.assertIn(
            "frame-ancestors 'none'",
            response.headers["Content-Security-Policy"],
        )


if __name__ == "__main__":
    unittest.main()
