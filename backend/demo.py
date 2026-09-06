"""Servidor de demonstração da Vercel, sem acesso ao SIGAA."""

import os
import secrets

from .app import create_app
from .production import _is_trusted_host

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo"

DEMO_UNITS = [
    {"value": "2151", "label": "CENTRO DE INFORMÁTICA"},
    {"value": "1355", "label": "CENTRO DE CIÊNCIAS EXATAS E DA NATUREZA"},
]

DEMO_ROWS = [
    {
        "disciplina": "INTRODUÇÃO À PROGRAMAÇÃO",
        "periodo": "2026.2",
        "turma": "01",
        "docente": "ANA LIMA",
        "tipo": "REGULAR",
        "forma": "Presencial",
        "situacao": "ABERTA",
        "horario": "24M23",
        "local": "LABORATÓRIO 1",
        "vagas": "12 vagas",
    },
    {
        "disciplina": "CÁLCULO DIFERENCIAL E INTEGRAL I",
        "periodo": "2026.2",
        "turma": "02",
        "docente": "BRUNO SOUSA",
        "tipo": "REGULAR",
        "forma": "Presencial",
        "situacao": "ABERTA",
        "horario": "35M23",
        "local": "SALA 204",
        "vagas": "8 vagas",
    },
    {
        "disciplina": "ESTRUTURAS DE DADOS",
        "periodo": "2026.2",
        "turma": "01",
        "docente": "CARLA MOURA",
        "tipo": "REGULAR",
        "forma": "Presencial",
        "situacao": "ABERTA",
        "horario": "24T23",
        "local": "LABORATÓRIO 2",
        "vagas": "5 vagas",
    },
    {
        "disciplina": "BANCO DE DADOS",
        "periodo": "2026.2",
        "turma": "01",
        "docente": "DANIEL ALVES",
        "tipo": "REGULAR",
        "forma": "Presencial",
        "situacao": "ABERTA",
        "horario": "3T23 6T45",
        "local": "SALA 101",
        "vagas": "10 vagas",
    },
]


class DemoSigaa:
    """Implementa o contrato do gateway usando somente dados sintéticos."""

    def login(self, username, password):
        if not (
            secrets.compare_digest(username, DEMO_USERNAME)
            and secrets.compare_digest(password, DEMO_PASSWORD)
        ):
            raise PermissionError("Login não confirmado. Use demo / demo.")

    def units(self):
        return [dict(unit) for unit in DEMO_UNITS]

    def query(self, year, period, unit, discipline="", teacher=""):
        def matches(row):
            return (
                row["periodo"] == f"{year}.{period}"
                and (not unit or unit == _row_unit(row))
                and discipline.casefold() in row["disciplina"].casefold()
                and teacher.casefold() in row["docente"].casefold()
            )

        return {
            "rows": [dict(row) for row in DEMO_ROWS if matches(row)],
            "units": self.units(),
        }


def _row_unit(row):
    if row["disciplina"] == "CÁLCULO DIFERENCIAL E INTEGRAL I":
        return "1355"
    return "2151"


class DemoSessionStore:
    """Sessão sem estado, adequada a funções serverless e sem dados pessoais."""

    TOKEN = "demo-session"

    def create(self, client):
        return self.TOKEN

    def get(self, session_id, refresh=True):
        return DemoSigaa() if secrets.compare_digest(session_id, self.TOKEN) else None

    def refresh(self, session_id):
        return secrets.compare_digest(session_id, self.TOKEN)

    def delete(self, session_id):
        return None


def make_demo_app(environment=None):
    """Cria uma prévia Vercel que nunca abre conexão com o SIGAA."""

    environment = os.environ if environment is None else environment
    if environment.get("APP_MODE") != "demo":
        raise ValueError("Modo de demonstração não habilitado.")
    if environment.get("VERCEL_ENV") == "production":
        raise ValueError("Modo de demonstração proibido em produção.")
    deployment_host = environment.get("VERCEL_URL")
    if not deployment_host or not _is_trusted_host(deployment_host):
        raise ValueError("Domínio da Vercel inválido.")
    configured_hosts = (deployment_host, environment.get("APP_HOST"))
    for host in configured_hosts:
        if host is not None and not _is_trusted_host(host):
            raise ValueError("Domínio da Vercel inválido.")
    hosts = tuple(dict.fromkeys(host for host in configured_hosts if host))

    return create_app(
        client_factory=DemoSigaa,
        sessions=DemoSessionStore(),
        secure_cookie=True,
        cookie_path="/api",
        valid_hosts=hosts,
        valid_origins=(None, *("https://" + host for host in hosts)),
    )
