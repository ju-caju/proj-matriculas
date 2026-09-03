import re
from http.cookiejar import CookieJar
from typing import Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .parser import SigaaPage


BASE = "https://sigaa.ufpb.br"
LOGIN = "/sigaa/logon.jsf"
QUERY = "/sigaa/ensino/turma/busca_turma.jsf"
PORTAL_PATHS = {
    "/sigaa/portais/discente/discente.jsf",
    "/sigaa/verportaldiscente.do",
}


class SigaaTransport(Protocol):
    def request(self, path, fields=None): ...


class SigaaClient(Protocol):
    def login(self, username, password): ...

    def units(self): ...

    def query(self, year, period, unit, discipline="", teacher=""): ...


class UrllibTransport:
    """Transporte HTTP com cookies isolados para uma sessão do SIGAA."""

    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, path, fields=None):
        data = urlencode(fields).encode() if fields is not None else None
        request = Request(
            BASE + path,
            data=data,
            headers={"User-Agent": "Mozilla/5.0", "Referer": BASE + path},
        )
        with self.opener.open(request, timeout=35) as response:
            raw = response.read()
            charset = response.headers.get_content_charset()
            if not charset:
                match = re.search(br'charset=["\s]*([a-zA-Z0-9-]+)', raw[:8000])
                charset = match.group(1).decode() if match else "utf-8"
            return response.url, SigaaPage(raw.decode(charset, errors="replace"))


class Sigaa:
    """Operações do portal usadas pelo planejador."""

    def __init__(self, transport=None):
        self.transport = transport or UrllibTransport()

    def login(self, username, password):
        _, login_page = self.transport.request(LOGIN)
        try:
            view_state = login_page.inputs["javax.faces.ViewState"]
        except KeyError as exc:
            raise PermissionError(
                "Login não confirmado. Confira usuário e senha no SIGAA."
            ) from exc
        fields = {
            "form": "form",
            "form:width": "1920",
            "form:height": "1080",
            "form:login": username,
            "form:senha": password,
            "form:entrar": login_page.inputs.get("form:entrar", "Entrar"),
            "javax.faces.ViewState": view_state,
        }
        url, result = self.transport.request(LOGIN, fields)
        destination = urlsplit(url)
        path = destination.path.lower()
        authenticated_page = (
            destination.scheme == "https"
            and destination.netloc == "sigaa.ufpb.br"
            and path in PORTAL_PATHS
            and "form:senha" not in result.inputs
            and "javax.faces.ViewState" in result.inputs
        )
        if not authenticated_page:
            raise PermissionError(
                "Login não confirmado. Confira usuário e senha no SIGAA."
            )
        try:
            self._validate_query_page(*self.transport.request(QUERY))
        except (PermissionError, ValueError) as exc:
            raise PermissionError(
                "Login não confirmado. Confira usuário e senha no SIGAA."
            ) from exc

    def units(self):
        url, page = self.transport.request(QUERY)
        self._validate_query_page(url, page)
        return page.units

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
            "javax.faces.ViewState": page.inputs["javax.faces.ViewState"],
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
        if not result.rows and "form:buttonBuscar" not in result.inputs:
            raise ValueError("O SIGAA retornou uma página inesperada. Tente novamente.")
        return {"rows": result.rows, "units": page.units}

    @staticmethod
    def _validate_query_page(url, page):
        if "form:senha" in page.inputs:
            raise PermissionError("Sua sessão expirou. Entre novamente.")
        destination = urlsplit(url)
        expected_page = (
            destination.scheme == "https"
            and destination.netloc == "sigaa.ufpb.br"
            and destination.path == QUERY
            and "javax.faces.ViewState" in page.inputs
            and "form:buttonBuscar" in page.inputs
        )
        if not expected_page:
            raise ValueError("O SIGAA retornou uma página inesperada. Tente novamente.")
