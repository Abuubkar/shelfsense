# The Python services: one build, one target per service (api, worker-enrich, worker-index, supplier-mock), which
# differ only in their start command. Follows uv's Docker guide: dependencies in their own layer, then our code,
# installed non-editable so the runtime stage needs only the virtualenv.
#   docker build --target api -t shelfsense-api .

FROM python:3.13-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Layer 1: third-party dependencies only; rebuilt when the lockfile changes. --all-packages: the supplier mock is
# a workspace member outside the root's dependencies.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=apps/api/pyproject.toml,target=apps/api/pyproject.toml \
    --mount=type=bind,source=apps/supplier_mock/pyproject.toml,target=apps/supplier_mock/pyproject.toml \
    --mount=type=bind,source=apps/worker_enrich/pyproject.toml,target=apps/worker_enrich/pyproject.toml \
    --mount=type=bind,source=apps/worker_index/pyproject.toml,target=apps/worker_index/pyproject.toml \
    --mount=type=bind,source=packages/clients/python/pyproject.toml,target=packages/clients/python/pyproject.toml \
    uv sync --frozen --all-packages --no-install-workspace --no-editable

# Layer 2: our code, as installed packages.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages --no-editable


FROM python:3.13-slim-trixie AS runtime

RUN useradd --create-home --uid 10001 shelfsense
WORKDIR /app
COPY --from=builder --chown=shelfsense /app/.venv /app/.venv
# Migrations ship with the image so a person can run `alembic upgrade head` as a one-off job; nothing applies them
# on start (docs/migrations.md).
COPY --chown=shelfsense alembic.ini /app/alembic.ini
COPY --chown=shelfsense apps/api/migrations /app/apps/api/migrations
# fastembed downloads its models on first use (bge-small ~130 MB; the reranker ~23 MB, API only). Mount a volume
# here to keep them across restarts; they aren't baked in (docs/backlog.md).
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 FASTEMBED_CACHE_PATH=/app/models
RUN mkdir /app/models && chown shelfsense /app/models
USER shelfsense


FROM runtime AS worker-enrich
CMD ["python", "-m", "shelfsense_worker_enrich"]

FROM runtime AS worker-index
CMD ["python", "-m", "shelfsense_worker_index"]

FROM runtime AS supplier-mock
EXPOSE 8030
CMD ["uvicorn", "shelfsense_supplier_mock:app", "--host", "0.0.0.0", "--port", "8030"]

# Last, so a plain `docker build .` gives the API image.
FROM runtime AS api
EXPOSE 8020
CMD ["uvicorn", "shelfsense_api.main:app", "--host", "0.0.0.0", "--port", "8020"]
