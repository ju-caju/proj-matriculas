import unittest
from pathlib import Path

from backend.parser import SigaaPage

FIXTURES = Path(__file__).parent / "fixtures"


class PageParserTest(unittest.TestCase):
    def test_parses_units_and_current_view_state(self):
        page = SigaaPage((FIXTURES / "units.html").read_text(encoding="utf-8"))

        self.assertEqual("view-units-123", page.inputs["javax.faces.ViewState"])
        self.assertEqual(
            [
                {"value": "0", "label": "Selecione"},
                {"value": "2151", "label": "CENTRO DE INFORMÁTICA"},
                {"value": "1234", "label": "CENTRO DE EDUCAÇÃO"},
            ],
            page.units,
        )

    def test_parses_class_rows_without_scripts_or_personal_data(self):
        page = SigaaPage((FIXTURES / "classes.html").read_text(encoding="utf-8"))

        self.assertEqual(
            [
                {
                    "disciplina": "CÁLCULO DIFERENCIAL (GRADUAÇÃO)",
                    "periodo": "2026.2",
                    "turma": "01",
                    "docente": "DOCENTE DE TESTE",
                    "tipo": "REGULAR",
                    "forma": "Presencial",
                    "situacao": "ABERTA",
                    "horario": "24M23",
                    "local": "SALA 1",
                    "vagas": "10 vagas",
                }
            ],
            page.rows,
        )

    def test_ignores_scripts_and_actions_inside_result_markup(self):
        page = SigaaPage(
            """
            <form>
              <input name="javax.faces.ViewState" value="safe-state">
              <input name="form:buttonBuscar" value="Buscar">
              <select name="form:selectUnidade">
                <option value="2151"><script>alert('x')</script>Centro seguro</option>
              </select>
              <table id="lista-turmas">
                <tr class="destaque">
                  <td><a href="javascript:acao()">DISCIPLINA SEGURA</a><script>acao()</script></td>
                </tr>
                <tr>
                  <td>2026.2</td><td>01</td><td>DOCENTE</td><td>REGULAR</td>
                  <td>Presencial</td><td>ABERTA</td><td>24M23</td><td>SALA</td>
                  <td>10 vagas</td>
                </tr>
              </table>
            </form>
            """
        )

        self.assertEqual([{"value": "2151", "label": "Centro seguro"}], page.units)
        self.assertEqual("DISCIPLINA SEGURA", page.rows[0]["disciplina"])
        self.assertNotIn("javascript", repr(page.rows))


if __name__ == "__main__":
    unittest.main()
