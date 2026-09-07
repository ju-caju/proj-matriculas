import unittest

from scripts.check_commits import invalid_subjects


class CommitMessageTest(unittest.TestCase):
    def test_accepts_conventional_commits_with_portuguese_subjects(self):
        subjects = [
            "feat: adicionar compromissos pessoais",
            "fix(grade): corrigir horários sobrepostos",
            "docs!: explicar nova configuração",
            "ci: validar mensagens de commit",
        ]

        self.assertEqual([], invalid_subjects(subjects))

    def test_rejects_invalid_structure_capitalization_and_final_period(self):
        subjects = [
            "corrigir aviso de conflito",
            "feature: adicionar horários",
            "fix: Corrigir horários",
            "fix: corrigir horários.",
            "fix corrigir horários",
        ]

        self.assertEqual(subjects, invalid_subjects(subjects))


if __name__ == "__main__":
    unittest.main()
