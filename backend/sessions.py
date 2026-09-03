import json
import secrets
import time
from typing import Protocol
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken


class SessionStore(Protocol):
    def create(self, client): ...

    def get(self, session_id, refresh=True): ...

    def refresh(self, session_id): ...

    def delete(self, session_id): ...


class MemorySessionStore:
    """Armazenamento local com expiração após 30 minutos sem uso."""

    def __init__(self, lifetime=1800, clock=time.time, token_factory=None):
        self.lifetime = lifetime
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._sessions = {}

    def create(self, client):
        session_id = self.token_factory()
        self._sessions[session_id] = (client, self.clock())
        return session_id

    def get(self, session_id, refresh=True):
        self._discard_expired()
        value = self._sessions.get(session_id)
        if value is None:
            return None
        client, _ = value
        if refresh:
            self.refresh(session_id)
        return client

    def refresh(self, session_id):
        value = self._sessions.get(session_id)
        if value is not None:
            self._sessions[session_id] = (value[0], self.clock())
            return True
        return False

    def delete(self, session_id):
        self._sessions.pop(session_id, None)

    def _discard_expired(self):
        now = self.clock()
        for session_id, (_, last_used) in list(self._sessions.items()):
            if now - last_used > self.lifetime:
                self._sessions.pop(session_id, None)


class RedisRestClient:
    """Cliente mínimo para a API REST compatível com Redis da Vercel/Upstash."""

    def __init__(self, url, token, timeout=5):
        if not url or not token:
            raise ValueError("Configuração do Redis ausente.")
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def execute(self, *command):
        request = Request(
            self.url,
            data=json.dumps(command).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read())
        if "error" in payload:
            raise ConnectionError("Operação do Redis falhou.")
        return payload.get("result")


class EncryptedRedisSessionStore:
    """Persiste apenas o estado temporário do SIGAA, cifrado e com TTL móvel."""

    def __init__(
        self,
        redis,
        encryption_key,
        client_loader,
        lifetime=1800,
        token_factory=None,
    ):
        if not encryption_key:
            raise ValueError("Chave de criptografia ausente.")
        try:
            self.cipher = Fernet(encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise ValueError("Chave de criptografia inválida.") from exc
        self.redis = redis
        self.client_loader = client_loader
        self.lifetime = lifetime
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    def create(self, client):
        session_id = self.token_factory()
        serialized = json.dumps(
            client.session_data(), ensure_ascii=True, separators=(",", ":")
        ).encode()
        encrypted = self.cipher.encrypt(serialized).decode()
        self.redis.execute("SET", self._key(session_id), encrypted, "EX", self.lifetime)
        return session_id

    def get(self, session_id, refresh=True):
        if not session_id:
            return None
        key = self._key(session_id)
        encrypted = self.redis.execute("GET", key)
        if encrypted is None:
            return None
        try:
            data = json.loads(self.cipher.decrypt(encrypted.encode()))
        except (InvalidToken, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Sessão inválida.") from exc
        if refresh and not self.refresh(session_id):
            return None
        return self.client_loader(data)

    def refresh(self, session_id):
        return bool(self.redis.execute("EXPIRE", self._key(session_id), self.lifetime))

    def delete(self, session_id):
        if session_id:
            self.redis.execute("DEL", self._key(session_id))

    @staticmethod
    def _key(session_id):
        return "session:" + session_id


class RedisRateLimiter:
    """Janela fixa compartilhada para tentativas de login."""

    SCRIPT = (
        "local n=redis.call('INCR',KEYS[1]); "
        "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"
    )

    def __init__(self, redis, limit=5, window=900):
        self.redis = redis
        self.limit = limit
        self.window = window

    def allow(self, client_ip):
        if not client_ip:
            raise ConnectionError("Endereço de origem não confiável.")
        count = self.redis.execute(
            "EVAL", self.SCRIPT, 1, "login:" + client_ip, self.window
        )
        return int(count) <= self.limit
