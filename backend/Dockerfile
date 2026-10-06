# syntax=docker/dockerfile:1.7
# One image, two modes: `scorecode api` and `scorecode worker` (decision D1).

FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
# WeasyPrint runtime libraries (pango/harfbuzz) + fonts for marksheets.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 fonts-dejavu-core fonts-noto-core curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra pdf --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --extra pdf

FROM base AS runtime
RUN groupadd --system --gid 10001 scorecode && useradd --system --uid 10001 --gid scorecode --home /app scorecode
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /src/app ./app
COPY --from=build /src/migrations ./migrations
COPY --from=build /src/alembic.ini ./
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH=/app
USER scorecode
EXPOSE 8000
CMD ["scorecode", "api", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --extra pdf --inexact
COPY tests ./tests
USER scorecode
