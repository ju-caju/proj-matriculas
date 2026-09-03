import unittest

from backend.parser import SigaaPage
from backend.sigaa import LOGIN, QUERY, Sigaa


def page(inputs="", body=""):
    return SigaaPage(f"<html><body><form>{inputs}{body}</form></body></html>")


class ControlledTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, path, fields=None):
        self.calls.append((path, fields))
        return self.responses.pop(0)


class SigaaTest(unittest.TestCase):
    def test_each_flow_uses_view_state_from_its_own_page(self):
        transport = ControlledTransport(
            [
                (
                    "https://sigaa.ufpb.br/sigaa/logon.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="login-state">'
                        '<input name="form:entrar" value="Entrar">'
                    ),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/portais/discente/discente.jsf",
                    page('<input name="javax.faces.ViewState" value="portal-state">'),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/ensino/turma/busca_turma.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="units-state">',
                        '<select name="form:selectUnidade">'
                        '<option value="2151">CENTRO DE INFORMÁTICA</option></select>',
                    ),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/ensino/turma/busca_turma.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="query-state">',
                        '<select name="form:selectUnidade">'
                        '<option value="2151">CENTRO DE INFORMÁTICA</option></select>',
                    ),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/ensino/turma/busca_turma.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="result-state">'
                        '<input name="form:buttonBuscar" value="Buscar">'
                    ),
                ),
            ]
        )
        client = Sigaa(transport)

        client.login("aluno", "segredo")
        units = client.units()
        result = client.query("2026", "2", "2151", "cálculo", "docente")

        self.assertEqual("login-state", transport.calls[1][1]["javax.faces.ViewState"])
        self.assertEqual(LOGIN, transport.calls[1][0])
        self.assertEqual([{"value": "2151", "label": "CENTRO DE INFORMÁTICA"}], units)
        self.assertEqual(QUERY, transport.calls[3][0])
        self.assertIsNone(transport.calls[3][1])
        self.assertEqual("query-state", transport.calls[4][1]["javax.faces.ViewState"])
        self.assertEqual("cálculo", transport.calls[4][1]["form:inputNomeDisciplina"])
        self.assertEqual("docente", transport.calls[4][1]["form:inputNomeDocente"])
        self.assertEqual([], result["rows"])

    def test_http_200_with_unexpected_page_does_not_confirm_login(self):
        transport = ControlledTransport(
            [
                (
                    "https://sigaa.ufpb.br/sigaa/logon.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="login-state">'
                        '<input name="form:entrar" value="Entrar">'
                    ),
                ),
                (
                    "https://outro-host.example/sigaa/portais/discente/discente.jsf",
                    page('<input name="javax.faces.ViewState" value="error-state">'),
                ),
            ]
        )

        with self.assertRaisesRegex(PermissionError, "Login não confirmado"):
            Sigaa(transport).login("aluno", "segredo")

    def test_http_200_at_unexpected_sigaa_route_does_not_confirm_login(self):
        transport = ControlledTransport(
            [
                (
                    "https://sigaa.ufpb.br/sigaa/logon.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="login-state">'
                        '<input name="form:entrar" value="Entrar">'
                    ),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/erro/discente-falso.jsf",
                    page('<input name="javax.faces.ViewState" value="error-state">'),
                ),
            ]
        )

        with self.assertRaisesRegex(PermissionError, "Login não confirmado"):
            Sigaa(transport).login("aluno", "segredo")

    def test_login_page_returned_during_query_means_expired_session(self):
        transport = ControlledTransport(
            [
                (
                    "https://sigaa.ufpb.br/sigaa/logon.jsf",
                    page('<input name="form:senha" value="">'),
                )
            ]
        )

        with self.assertRaisesRegex(PermissionError, "sessão expirou"):
            Sigaa(transport).units()


if __name__ == "__main__":
    unittest.main()
