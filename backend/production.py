import ipaddress
import os
import re

from .app import create_app
from .sessions import EncryptedRedisSessionStore, RedisRateLimiter, RedisRestClient
from .sigaa import Sigaa


def vercel_client_ip(request):
    """Aceita somente o cabeçalho que a Vercel sobrescreve na borda."""
    value = request.headers.get("X-Vercel-Forwarded-For", "")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ConnectionError("Endereço de origem não confiável.") from exc


def _production_dependencies(environment):
    environment = os.environ if environment is None else environment
    redis = RedisRestClient(
        environment.get("KV_REST_API_URL"),
        environment.get("KV_REST_API_TOKEN"),
    )
    sessions = EncryptedRedisSessionStore(
        redis,
        environment.get("SESSION_ENCRYPTION_KEY"),
        Sigaa.from_session_data,
    )
    deployment_host = environment.get("VERCEL_URL")
    if not deployment_host:
        raise ValueError("Domínio da Vercel ausente.")
    for host in (
        deployment_host,
        environment.get("VERCEL_PROJECT_PRODUCTION_URL"),
    ):
        if host is not None and not _is_trusted_host(host):
            raise ValueError("Domínio da Vercel inválido.")
    hosts = tuple(
        dict.fromkeys(
            host
            for host in (
                deployment_host,
                environment.get("VERCEL_PROJECT_PRODUCTION_URL"),
            )
            if host
        )
    )
    return redis, sessions, hosts


def _is_trusted_host(value):
    """Accept only a DNS host, never a URL, port, or header fragment."""
    if not isinstance(value, str) or len(value) > 253:
        return False
    labels = value.rstrip(".").split(".")
    return bool(labels) and all(
        label
        and len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )


def make_production_app(environment=None):
    """Build the FastAPI application with the production dependencies."""
    redis, sessions, hosts = _production_dependencies(environment)
    return create_app(
        client_factory=Sigaa,
        sessions=sessions,
        login_limiter=RedisRateLimiter(redis),
        client_ip=vercel_client_ip,
        secure_cookie=True,
        cookie_path="/api",
        valid_hosts=hosts,
        valid_origins=(None, *("https://" + host for host in hosts)),
    )
