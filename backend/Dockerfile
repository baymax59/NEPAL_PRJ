# The backend API as a container image (Step 14.1).
# Built and started by:  docker compose --profile app up -d --build   (from the project root)
FROM python:3.12.16-slim-trixie

# uv installs exactly the package versions recorded in uv.lock (PyTorch: the CPU-only build).
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /srv/case-search/backend
# Packages first: this slow layer is reused as long as pyproject.toml and uv.lock don't change.
# The download cache is mounted only during the build, so it doesn't stay in the image (1.4 GB).
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
COPY . .

# Run as an ordinary user, not root. data/ (uploads, downloads) and models/ are volumes.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /srv/case-search/data /srv/case-search/models \
 && chown app /srv/case-search/data /srv/case-search/models
USER app

EXPOSE 8000
# Bring the database tables up to date, then serve the API. --proxy-headers: the audit log records
# the user's address, not the web server's. Safe because only the web server can reach this port.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
