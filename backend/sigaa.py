import re
from http.cookiejar import Cookie, CookieJar
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from .parser import SigaaPage

BASE = "https://sigaa.ufpb.br"
LOGIN = "/sigaa/logon.jsf"
QUERY = "/sigaa/ensino/turma/busca_turma.jsf"
SIGAA_HOST = "sigaa.ufpb.br"
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class SigaaError(Exception):
    """Base for failures that can safely cross the SIGAA boundary."""


class SigaaAuthenticationError(PermissionError, SigaaError):
    """The portal requires a login or rejected the supplied credentials."""


class SigaaUnexpectedPageError(ValueError, SigaaError):
    """The portal returned a page outside the supported form contract."""


class SigaaTransportError(ConnectionError, SigaaError):
    """The portal could not be reached or its response exceeded a limit."""


class SigaaResponseTooLarge(SigaaTransportError):
    """The response was rejected before HTML parsing due to its size."""


def _is_allowed_url(url: str, allowed_hosts: frozenset[str]) -> bool:
    try:
        destination = urlsplit(url)
        return (
            destination.scheme == "https"
            and destination.hostname is not None
            and destination.hostname.lower() in allowed_hosts
            and destination.port in (None, 443)
            and destination.username is None
            and destination.password is None
        )
    except ValueError:
        return False


class AllowlistRedirectHandler(HTTPRedirectHandler):
    """Follow only HTTPS redirects to explicitly configured SIGAA hosts."""

    def __init__(self, allowed_hosts=(SIGAA_HOST,)):
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_allowed_url(newurl, self.allowed_hosts):
            raise URLError("Redirecionamento do SIGAA não permitido.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SigaaTransport(Protocol):
    def request(self, path: str, fields: dict[str, Any] | None = None): ...


class SigaaClient(Protocol):
    def login(self, username, password): ...

    def units(self): ...

    def query(self, year, period, unit, discipline="", teacher=""): ...


class UrllibTransport:
    """Transporte HTTP com cookies isolados para uma sessão do SIGAA."""

    def __init__(
        self,
        cookiejar=None,
        *,
        allowed_hosts=(SIGAA_HOST,),
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=READ_TIMEOUT,
        max_response_bytes=MAX_RESPONSE_BYTES,
    ):
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("Timeout do SIGAA deve ser positivo.")
        if max_response_bytes <= 0:
            raise ValueError("Limite de resposta do SIGAA deve ser positivo.")
        self.cookiejar = cookiejar or CookieJar()
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        if not self.allowed_hosts:
            raise ValueError("A lista de hosts permitidos está vazia.")
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_response_bytes = max_response_bytes
        self.opener = build_opener(
            HTTPCookieProcessor(self.cookiejar),
            AllowlistRedirectHandler(self.allowed_hosts),
        )

    def request(self, path: str, fields: dict[str, Any] | None = None):
        if not path.startswith("/") or path.startswith("//"):
            raise SigaaUnexpectedPageError("Rota do SIGAA não permitida.")
        data = urlencode(fields).encode() if fields is not None else None
        request = Request(
            BASE + path,
            data=data,
            headers={"User-Agent": "Mozilla/5.0", "Referer": BASE + path},
        )
        try:
            with self.opener.open(request, timeout=self.connect_timeout) as response:
                if not _is_allowed_url(response.url, self.allowed_hosts):
                    raise SigaaUnexpectedPageError(
                        "Redirecionamento do SIGAA não permitido."
                    )
                self._set_read_timeout(response)
                raw = self._read_limited(response)
                charset = response.headers.get_content_charset()
                if not charset:
                    match = re.search(rb'charset=["\s]*([a-zA-Z0-9-]+)', raw[:8000])
                    charset = match.group(1).decode() if match else "utf-8"
                return response.url, SigaaPage(raw.decode(charset, errors="replace"))
        except SigaaError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise SigaaTransportError(
                "Não foi possível consultar o SIGAA. Tente novamente."
            ) from exc

    def _read_limited(self, response):
        chunks = []
        total = 0
        while True:
            chunk = response.read(min(65536, self.max_response_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > self.max_response_bytes:
                raise SigaaResponseTooLarge(
                    "A resposta do SIGAA excedeu o limite permitido."
                )
        return b"".join(chunks)

    def _set_read_timeout(self, response):
        """Set a distinct socket read deadline when urllib exposes its socket."""
        socket = getattr(
            getattr(getattr(response, "fp", None), "raw", None), "_sock", None
        )
        if socket is not None and hasattr(socket, "settimeout"):
            socket.settimeout(self.read_timeout)


class Sigaa:
    """Operações do portal usadas pelo planejador."""

    def __init__(self, transport=None):
        self.transport = transport or UrllibTransport()

    def session_data(self):
        cookies = []
        for cookie in self.transport.cookiejar:
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "expires": cookie.expires,
                }
            )
        return {"cookies": cookies}

    @classmethod
    def from_session_data(cls, data):
        jar = CookieJar()
        for item in data.get("cookies", []):
            jar.set_cookie(
                Cookie(
                    version=0,
                    name=item["name"],
                    value=item["value"],
                    port=None,
                    port_specified=False,
                    domain=item["domain"],
                    domain_specified=bool(item["domain"]),
                    domain_initial_dot=item["domain"].startswith("."),
                    path=item["path"],
                    path_specified=True,
                    secure=bool(item["secure"]),
                    expires=item["expires"],
                    discard=item["expires"] is None,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )
        return cls(UrllibTransport(jar))

    def login(self, username, password):
        login_url, login_page = self.transport.request(LOGIN)
        if not _is_allowed_url(login_url, frozenset((SIGAA_HOST,))):
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            )
        try:
            login_inputs = self._page_inputs(login_page)
        except SigaaUnexpectedPageError as exc:
            raise SigaaAuthenticationError(
                "Falha no login, etapa 1: o SIGAA não apresentou o formulário esperado."
            ) from exc
        try:
            view_state = login_inputs["javax.faces.ViewState"]
        except KeyError as exc:
            raise SigaaAuthenticationError(
                "Falha no login, etapa 1: o SIGAA não apresentou o formulário esperado."
            ) from exc
        fields = {
            "form": "form",
            "form:width": "1920",
            "form:height": "1080",
            "form:login": username,
            "form:senha": password,
            "form:entrar": login_inputs.get("form:entrar", "Entrar"),
            "javax.faces.ViewState": view_state,
        }
        url, result = self.transport.request(LOGIN, fields)
        try:
            result_inputs = self._page_inputs(result)
        except SigaaUnexpectedPageError as exc:
            raise SigaaAuthenticationError(
                "Falha no login, etapa 2B: o SIGAA devolveu a tela de login."
            ) from exc
        authenticated_page = (
            _is_allowed_url(url, frozenset((SIGAA_HOST,)))
            and "form:senha" not in result_inputs
        )
        if not authenticated_page:
            if not _is_allowed_url(url, frozenset((SIGAA_HOST,))):
                detail = "2A: o redirecionamento saiu do domínio do SIGAA"
            else:
                detail = "2B: o SIGAA devolveu a tela de login"
            raise SigaaAuthenticationError("Falha no login, etapa " + detail + ".")
        try:
            self._validate_query_page(*self.transport.request(QUERY))
        except (PermissionError, ValueError) as exc:
            raise SigaaAuthenticationError(
                "Falha no login, etapa 3: a autenticação ocorreu, mas o SIGAA "
                "não abriu a consulta de turmas."
            ) from exc

    def units(self):
        url, page = self.transport.request(QUERY)
        self._validate_query_page(url, page)
        return self._page_units(page)

    def query(self, year, period, unit, discipline="", teacher=""):
        url, page = self.transport.request(QUERY)
        self._validate_query_page(url, page)
        fields = {
            "form": "form",
            "form:checkNivel": "on",
            "form:selectNivelTurma": "G",
            "form:checkAnoPeriodo": "on",
            "form:inputAno": year,
            "form:inputPeriodo": period,
            "form:selectUnidade": unit or "0",
            "form:selectModalidade": "0",
            "form:selectCurso": "0",
            "form:formaEnsino": "0",
            "form:selectSituacaoTurma": "1",
            "form:selectTipoTurma": "0",
            "form:selectOpcaoOrdenacao": "1",
            "turmasEAD": "false",
            "form:buttonBuscar": "Buscar",
            "javax.faces.ViewState": self._required_view_state(page),
        }
        for field in (
            "CodDisciplina",
            "CodTurma",
            "Local",
            "Horario",
            "NomeDisciplina",
            "NomeDocente",
        ):
            fields["form:input" + field] = ""
        if unit:
            fields["form:checkUnidade"] = "on"
        if discipline:
            fields["form:checkDisciplina"] = "on"
            fields["form:inputNomeDisciplina"] = discipline
        if teacher:
            fields["form:checkDocente"] = "on"
            fields["form:inputNomeDocente"] = teacher
        result_url, result = self.transport.request(QUERY, fields)
        self._validate_query_page(result_url, result)
        result_inputs = self._page_inputs(result)
        rows = getattr(result, "rows", None)
        if not isinstance(rows, list):
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            )
        if not rows and "form:buttonBuscar" not in result_inputs:
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            )
        return {"rows": rows, "units": self._page_units(page)}

    @staticmethod
    def _page_inputs(page):
        inputs = getattr(page, "inputs", None)
        if not isinstance(inputs, dict):
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            )
        return inputs

    @classmethod
    def _required_view_state(cls, page):
        try:
            return cls._page_inputs(page)["javax.faces.ViewState"]
        except KeyError as exc:
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            ) from exc

    @staticmethod
    def _page_units(page):
        units = getattr(page, "units", None)
        if not isinstance(units, list):
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            )
        return units

    @staticmethod
    def _validate_query_page(url, page):
        inputs = Sigaa._page_inputs(page)
        if "form:senha" in inputs:
            raise SigaaAuthenticationError("Sua sessão expirou. Entre novamente.")
        expected_page = (
            _is_allowed_url(url, frozenset((SIGAA_HOST,)))
            and urlsplit(url).path == QUERY
            and "javax.faces.ViewState" in inputs
            and "form:buttonBuscar" in inputs
        )
        if not expected_page:
            raise SigaaUnexpectedPageError(
                "O SIGAA retornou uma página inesperada. Tente novamente."
            )
