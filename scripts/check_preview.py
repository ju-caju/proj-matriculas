#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
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


def request(base_url, path, *, data=None, origin=None, content_type=None):
    headers = {}
    if origin:
        headers["Origin"] = origin
    if content_type:
        headers["Content-Type"] = content_type
    payload = data.encode() if data is not None else None
    req = Request(urljoin(base_url + "/", path.lstrip("/")), payload, headers)
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return Response(response.status, response.headers, response.read())


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def require_security_headers(response, path):
    for name, expected in SECURITY_HEADERS.items():
        actual = response.headers.get(name, "")
        require(expected in actual, f"{path}: cabeçalho {name} ausente ou inválido")


def require_json_response(response, status, body, label):
    require(response.status == status, f"{label}: esperado {status}, recebido {response.status}")
    require(
        response.headers.get_content_type() == "application/json",
        f"{label}: Content-Type não é application/json",
    )
    require(response.json() == body, f"{label}: corpo JSON inesperado")


def check_preview(base_url):
    base_url = base_url.rstrip("/")
    parsed = urlsplit(base_url)
    require(parsed.scheme == "https" and parsed.netloc, "use uma URL HTTPS completa")
    origin = f"{parsed.scheme}://{parsed.netloc}"

    page = request(base_url, "/")
    require(page.status == 200, f"/: esperado 200, recebido {page.status}")
    require(b"Minha grade" in page.body, "/: a interface esperada não foi encontrada")
    require_security_headers(page, "/")

    session = request(base_url, "/api/session")
    require_json_response(
        session,
        200,
        {"authenticated": False, "expired": False},
        "/api/session",
    )
    require_security_headers(session, "/api/session")

    invalid_json = request(
        base_url,
        "/api/login",
        data="{}",
        origin=origin,
        content_type="text/plain",
    )
    require_json_response(
        invalid_json,
        415,
        {"error": "JSON necessário."},
        "validação JSON",
    )

    invalid_origin = request(
        base_url,
        "/api/login",
        data="{}",
        origin="https://origem-invalida.example",
        content_type="application/json",
    )
    require_json_response(
        invalid_origin,
        403,
        {"error": "Origem inválida."},
        "origem inválida",
    )

    probe = json.dumps({"preview_probe": True})
    for attempt in range(1, 6):
        response = request(
            base_url,
            "/api/login",
            data=probe,
            origin=origin,
            content_type="application/json",
        )
        require_json_response(
            response,
            400,
            {"error": "Dados inválidos ou resposta inesperada do SIGAA."},
            f"rate limit, tentativa {attempt}",
        )
    limited = request(
        base_url,
        "/api/login",
        data=probe,
        origin=origin,
        content_type="application/json",
    )
    require_json_response(
        limited,
        429,
        {"error": "Muitas tentativas de login. Tente novamente mais tarde."},
        "rate limit, tentativa 6",
    )


def check_unconfigured_preview(base_url):
    page = request(base_url.rstrip("/"), "/")
    require(page.status == 200, f"/: esperado 200, recebido {page.status}")
    require_security_headers(page, "/")
    session = request(base_url.rstrip("/"), "/api/session")
    require_json_response(
        session,
        503,
        {"error": "Serviço temporariamente indisponível."},
        "/api/session",
    )
    require_security_headers(session, "/api/session")


def main():
    parser = argparse.ArgumentParser(
        description="Valida uma prévia da aplicação sem acessar o SIGAA."
    )
    parser.add_argument("url", help="URL HTTPS da prévia")
    parser.add_argument(
        "--sem-configuracao",
        action="store_true",
        help="confirma que uma prévia sem segredos falha de modo fechado",
    )
    args = parser.parse_args()
    if args.sem_configuracao:
        check_unconfigured_preview(args.url)
        print("Falha fechada da prévia confirmada.")
    else:
        check_preview(args.url)
        print("Prévia validada sem credenciais e sem acesso ao SIGAA.")


if __name__ == "__main__":
    main()
