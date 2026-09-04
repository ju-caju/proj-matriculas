import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CiWorkflowTest(unittest.TestCase):
    def test_checkout_keeps_history_required_by_gitleaks(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        checkout = workflow.index("uses: actions/checkout@")
        gitleaks = workflow.index("uses: gitleaks/gitleaks-action@")
        setup = workflow[checkout:gitleaks]

        self.assertIn("fetch-depth: 0", setup)


if __name__ == "__main__":
    unittest.main()
