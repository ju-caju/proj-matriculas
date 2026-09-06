"""Vercel ASGI entrypoint for production and isolated demo previews."""

import os

from backend.app import unavailable_app
from backend.demo import make_demo_app
from backend.production import make_production_app

try:
    if os.environ.get("APP_MODE") == "demo":
        app = make_demo_app()
    else:
        app = make_production_app()
except ValueError:
    # Configuration errors must never expose which production secret is absent.
    app = unavailable_app()
