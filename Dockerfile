# Local development image. Production deployments continue to use api/index.py
# through Vercel; this image deliberately uses the explicit in-memory adapter.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
RUN useradd --create-home --uid 10001 app

# Install only locked runtime dependencies into the image's virtualenv.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY --chown=app:app . .
RUN chown -R app:app /app
USER app

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3)"

CMD ["uv", "run", "--no-sync", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8765"]
