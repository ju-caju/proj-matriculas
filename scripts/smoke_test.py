"""Check the local HTTP contract without credentials or SIGAA traffic."""

import argparse
import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

SECURITY_HEADERS = {
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@dataclass
class Response:
    status: int
    headers: object
    body: bytes

    def json(self):
        return json.loads(self.body)


def request(base_url: str, path: str, *, data: str | None = None, content_type=None):
    headers = {"Content-Type": content_type} if content_type else {}
    payload = data.encode() if data is not None else None
    req = Request(
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/")), payload, headers
    )
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return Response(response.status, response.headers, response.read())


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def require_security_headers(response: Response, path: str):
    for name, expected in SECURITY_HEADERS.items():
        require(
            expected in response.headers.get(name, ""),
            f"{path}: cabeçalho {name} ausente ou inválido",
        )


def require_json(response: Response, expected_status: int, expected_body, label: str):
    require(response.status == expected_status, f"{label}: status inesperado")
    require(
        response.headers.get_content_type() == "application/json",
        f"{label}: Content-Type inesperado",
    )
    require(response.json() == expected_body, f"{label}: corpo inesperado")


def check(base_url: str):
    parsed = urlsplit(base_url)
    require(parsed.scheme in ("http", "https") and parsed.netloc, "URL inválida")

    page = request(base_url, "/")
    require(page.status == 200, "página: status inesperado")
    require(b"Minha grade" in page.body, "página: interface esperada ausente")
    require_security_headers(page, "/")

    health = request(base_url, "/api/health")
    require_json(health, 200, {"status": "ok"}, "/api/health")
    require_security_headers(health, "/api/health")

    session = request(base_url, "/api/session")
    require_json(
        session,
        200,
        {"authenticated": False, "expired": False},
        "/api/session",
    )
    require_security_headers(session, "/api/session")

    # Reaches only the HTTP validation boundary; no credentials are supplied.
    invalid_login = request(
        base_url,
        "/api/login",
        data="{}",
        content_type="text/plain",
    )
    require_json(invalid_login, 415, {"error": "JSON necessário."}, "login inválido")
    require_security_headers(invalid_login, "/api/login")


def main():
    parser = argparse.ArgumentParser(
        description="Valida a aplicação local sem credenciais e sem SIGAA."
    )
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    check(args.url)
    print("Smoke test concluído sem credenciais e sem acesso ao SIGAA.")


if __name__ == "__main__":
    main()
