# syntax=docker/dockerfile:1

# ---------- Estágio 1: dependências -------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Instala só as dependências (camada cacheada enquanto o uv.lock não mudar).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# ---------- Estágio 2: imagem final -------------------------------------------
FROM python:3.12-slim AS runtime

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --home-dir /app app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PORT=8000

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app . /app

# collectstatic no build. As variáveis abaixo existem só neste RUN (valores fictícios,
# necessários apenas para carregar os settings) e não ficam na imagem.
RUN DJANGO_SECRET_KEY=collectstatic-build-only \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput \
    && chmod +x docker/entrypoint.sh \
    && chown -R app:app /app/staticfiles

# Commit da imagem, exposto no /api/health/ ("versao"). O Easypanel passa GIT_SHA como
# build arg nos deploys a partir do repositório. Declarado só aqui, no fim, para não
# invalidar o cache das camadas anteriores.
ARG GIT_SHA=""
ENV GIT_SHA=${GIT_SHA}

USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "-c", "config/gunicorn.conf.py", "config.wsgi:application"]
