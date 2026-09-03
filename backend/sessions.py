import secrets
import time
from typing import Protocol


class SessionStore(Protocol):
    def create(self, client): ...

    def get(self, session_id): ...

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

    def get(self, session_id):
        self._discard_expired()
        value = self._sessions.get(session_id)
        if value is None:
            return None
        client, _ = value
        self._sessions[session_id] = (client, self.clock())
        return client

    def delete(self, session_id):
        self._sessions.pop(session_id, None)

    def _discard_expired(self):
        now = self.clock()
        for session_id, (_, last_used) in list(self._sessions.items()):
            if now - last_used > self.lifetime:
                self._sessions.pop(session_id, None)
