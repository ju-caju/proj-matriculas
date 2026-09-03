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
                        '<input name="javax.faces.ViewState" value="confirmation-state">'
                        '<input name="form:buttonBuscar" value="Buscar">'
                    ),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/ensino/turma/busca_turma.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="units-state">'
                        '<input name="form:buttonBuscar" value="Buscar">',
                        '<select name="form:selectUnidade">'
                        '<option value="2151">CENTRO DE INFORMÁTICA</option></select>',
                    ),
                ),
                (
                    "https://sigaa.ufpb.br/sigaa/ensino/turma/busca_turma.jsf",
                    page(
                        '<input name="javax.faces.ViewState" value="query-state">'
                        '<input name="form:buttonBuscar" value="Buscar">',
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
        self.assertEqual(QUERY, transport.calls[4][0])
        self.assertIsNone(transport.calls[4][1])
        self.assertEqual("query-state", transport.calls[5][1]["javax.faces.ViewState"])
        self.assertEqual("cálculo", transport.calls[5][1]["form:inputNomeDisciplina"])
        self.assertEqual("docente", transport.calls[5][1]["form:inputNomeDocente"])
        self.assertEqual([], result["rows"])

    def test_http_200_with_unexpected_page_does_not_confirm_login(self):
        invalid_destinations = (
            "https://outro-host.example/sigaa/portais/discente/discente.jsf",
            "https://sigaa.ufpb.br/sigaa/erro/discente-falso.jsf",
            "https://sigaa.ufpb.br/sigaa/portais/discente/erro.jsf",
        )
        for destination in invalid_destinations:
            with self.subTest(destination=destination):
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
                            destination,
                            page(
                                '<input name="javax.faces.ViewState" '
                                'value="error-state">'
                            ),
                        ),
                    ]
                )

                with self.assertRaisesRegex(PermissionError, "etapa 2"):
                    Sigaa(transport).login("aluno", "segredo")

    def test_units_rejects_external_or_unexpected_pages(self):
        unexpected_pages = (
            (
                "https://outro-host.example/sigaa/ensino/turma/busca_turma.jsf",
                page(
                    '<input name="javax.faces.ViewState" value="query-state">'
                    '<input name="form:buttonBuscar" value="Buscar">'
                ),
            ),
            (
                "https://sigaa.ufpb.br/sigaa/ensino/turma/busca_turma.jsf",
                page('<input name="javax.faces.ViewState" value="query-state">'),
            ),
        )
        for response in unexpected_pages:
            with self.subTest(url=response[0]):
                with self.assertRaisesRegex(ValueError, "página inesperada"):
                    Sigaa(ControlledTransport([response])).units()

    def test_login_rejects_portal_page_when_protected_form_is_unavailable(self):
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
                    page('<input name="javax.faces.ViewState" value="error-state">'),
                ),
            ]
        )

        with self.assertRaisesRegex(PermissionError, "etapa 3"):
            Sigaa(transport).login("aluno", "segredo")

    def test_login_reports_when_initial_form_is_unavailable(self):
        transport = ControlledTransport(
            [("https://sigaa.ufpb.br/sigaa/logon.jsf", page())]
        )

        with self.assertRaisesRegex(PermissionError, "etapa 1"):
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
