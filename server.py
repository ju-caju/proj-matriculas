"""Aplicação local, sem dependências externas. Execute: python3 server.py."""

from http.server import HTTPServer

from backend.http import make_handler
from backend.sessions import MemorySessionStore
from backend.sigaa import Sigaa

Handler = make_handler(Sigaa, MemorySessionStore())


if __name__ == "__main__":
    print("Aplicação disponível em http://127.0.0.1:8765", flush=True)
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
