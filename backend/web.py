"""Shared HTTP constants for the ASGI application."""

from pathlib import Path

ROOT = Path(__file__).parent.parent
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'",
    ),
)
