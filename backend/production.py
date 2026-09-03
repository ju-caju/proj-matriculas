import ipaddress
import os

from .http import make_handler
from .sessions import EncryptedRedisSessionStore, RedisRateLimiter, RedisRestClient
from .sigaa import Sigaa


def vercel_client_ip(request):
    """Aceita somente o cabeçalho que a Vercel sobrescreve na borda."""
    value = request.headers.get("X-Vercel-Forwarded-For", "")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ConnectionError("Endereço de origem não confiável.") from exc


def make_production_handler(environment=None):
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
    return make_handler(
        Sigaa,
        sessions,
        login_limiter=RedisRateLimiter(redis),
        client_ip=vercel_client_ip,
        secure_cookie=True,
        cookie_path="/api",
        valid_hosts=hosts,
        valid_origins=(None, *("https://" + host for host in hosts)),
    )
