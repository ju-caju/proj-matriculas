import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_static import STATIC_FILES, validate


class StaticValidationTest(unittest.TestCase):
    def _root(self, index='<script src="/app.js"></script>'):
        root = Path(tempfile.mkdtemp())
        for filename in STATIC_FILES:
            path = root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("asset", encoding="utf-8")
        (root / "index.html").write_text(index, encoding="utf-8")
        (root / "vercel.json").write_text(
            json.dumps(
                {
                    "functions": {"api/index.py": {}},
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_accepts_static_bundle_and_single_vercel_entrypoint(self):
        validate(self._root())

    def test_rejects_unknown_local_reference(self):
        with self.assertRaisesRegex(AssertionError, "referências locais"):
            validate(self._root('<script src="/missing.js"></script>'))

    def test_rejects_empty_static_asset(self):
        root = self._root()
        (root / "style.css").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "arquivos estáticos vazios"):
            validate(root)


if __name__ == "__main__":
    unittest.main()
