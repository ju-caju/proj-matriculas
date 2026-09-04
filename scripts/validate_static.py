"""Validate the static bundle and Vercel route without a network or SIGAA call."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_FILES = {
    "index.html",
    "style.css",
    "app.js",
    "schedule.js",
    "frontend/dom.js",
    "frontend/plan-store.js",
    "frontend/api-client.js",
    "frontend/grade-image.js",
}
LOCAL_REFERENCE = re.compile(r'(?:src|href)="(/[^"#?]+)"')


def validate(root: Path = ROOT) -> None:
    missing = sorted(path for path in STATIC_FILES if not (root / path).is_file())
    if missing:
        raise AssertionError("arquivos estáticos ausentes: " + ", ".join(missing))
    empty = sorted(
        path for path in STATIC_FILES if not (root / path).read_bytes().strip()
    )
    if empty:
        raise AssertionError("arquivos estáticos vazios: " + ", ".join(empty))

    index = (root / "index.html").read_text(encoding="utf-8")
    references = {value.lstrip("/") for value in LOCAL_REFERENCE.findall(index)}
    unknown = sorted(references - STATIC_FILES)
    if unknown:
        raise AssertionError("referências locais desconhecidas: " + ", ".join(unknown))

    config = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
    if set(config.get("functions", {})) != {"api/index.py"}:
        raise AssertionError("api/index.py deve ser o único entrypoint Vercel")
    if "rewrites" in config:
        raise AssertionError("o preset FastAPI não deve reescrever as rotas")


if __name__ == "__main__":
    validate()
    print("Validação estática concluída.")
