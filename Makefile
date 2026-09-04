.PHONY: install format format-check lint typecheck test coverage audit build smoke-test check

install:
	uv sync --locked

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .

typecheck:
	uv run mypy

test:
	uv run python -m unittest discover -v
	node schedule.test.js
	node frontend/plan-store.test.js
	node frontend/api-client.test.js

coverage:
	uv run coverage run -m unittest discover
	uv run coverage report

audit:
	uv export --locked --no-dev --format requirements.txt | uvx --from pip-audit pip-audit --strict -r /dev/stdin

build:
	uv run python scripts/validate_static.py

smoke-test:
	uv run python scripts/smoke_test.py

check: format-check lint typecheck test coverage audit build
