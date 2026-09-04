.PHONY: install format format-check lint typecheck test coverage check

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

coverage:
	uv run coverage run -m unittest discover
	uv run coverage report

check: format-check lint typecheck test coverage
