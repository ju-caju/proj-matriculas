import importlib.util
import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ENTRYPOINT = Path(__file__).parent.parent / "api" / "index.py"
API_ROOT = ENTRYPOINT.parent
VERCEL_CONFIG = Path(__file__).parent.parent / "vercel.json"
PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


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
        project = tomllib.loads(PYPROJECT.read_text())

        self.assertEqual("fastapi", config["framework"])
        self.assertEqual("api.index:app", project["tool"]["vercel"]["entrypoint"])
        self.assertEqual({"api/index.py"}, set(config["functions"]))
        self.assertNotIn("rewrites", config)

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

    def test_demo_preview_uses_the_simulated_backend(self):
        spec = importlib.util.spec_from_file_location("vercel_demo", ENTRYPOINT)
        module = importlib.util.module_from_spec(spec)
        environment = {
            "APP_MODE": "demo",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "demo.example.vercel.app",
        }
        with patch.dict(os.environ, environment, clear=True):
            spec.loader.exec_module(module)

        response = TestClient(module.app).post(
            "/api/login",
            json={"username": "demo", "password": "demo"},
            headers={
                "host": "demo.example.vercel.app",
                "origin": "https://demo.example.vercel.app",
            },
        )

        self.assertEqual(200, response.status_code)

    def test_demo_preview_accepts_its_configured_public_alias(self):
        spec = importlib.util.spec_from_file_location("vercel_demo_alias", ENTRYPOINT)
        module = importlib.util.module_from_spec(spec)
        environment = {
            "APP_MODE": "demo",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "temporary.example.vercel.app",
            "APP_HOST": "demo.example.vercel.app",
        }
        with patch.dict(os.environ, environment, clear=True):
            spec.loader.exec_module(module)

        response = TestClient(module.app).get(
            "/api/session",
            headers={"host": "demo.example.vercel.app"},
        )

        self.assertEqual(200, response.status_code)

    def test_demo_mode_fails_closed_in_a_production_deployment(self):
        spec = importlib.util.spec_from_file_location("vercel_demo_prod", ENTRYPOINT)
        module = importlib.util.module_from_spec(spec)
        environment = {
            "APP_MODE": "demo",
            "VERCEL_ENV": "production",
            "VERCEL_URL": "prod.example.vercel.app",
        }
        with patch.dict(os.environ, environment, clear=True):
            spec.loader.exec_module(module)

        response = TestClient(module.app).get("/api/session")

        self.assertEqual(503, response.status_code)

    def test_demo_preview_rejects_an_invalid_public_alias(self):
        spec = importlib.util.spec_from_file_location(
            "vercel_demo_bad_alias", ENTRYPOINT
        )
        module = importlib.util.module_from_spec(spec)
        environment = {
            "APP_MODE": "demo",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "temporary.example.vercel.app",
            "APP_HOST": "https://unsafe.example/redirect",
        }
        with patch.dict(os.environ, environment, clear=True):
            spec.loader.exec_module(module)

        response = TestClient(module.app).get("/api/session")

        self.assertEqual(503, response.status_code)


if __name__ == "__main__":
    unittest.main()
