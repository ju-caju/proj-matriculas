"""Vercel ASGI entrypoint for the complete FastAPI application."""

from backend.app import unavailable_app
from backend.production import make_production_app

try:
    app = make_production_app()
except ValueError:
    # Configuration errors must never expose which production secret is absent.
    app = unavailable_app()
