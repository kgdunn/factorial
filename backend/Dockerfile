FROM python:3.14-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System dependencies:
#   - WeasyPrint needs Pango, Cairo, and GDK-PixBuf to render PDFs.
#   - Playwright (used to pre-render ECharts plots for the PDF) pulls in
#     a Chromium binary via `playwright install chromium` plus the shared
#     libraries it needs to run headless.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files and project metadata referenced by pyproject.toml
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev extras)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code and report templates
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY templates/ templates/

# Install the project itself
RUN uv sync --frozen --no-dev

# Install the Chromium binary Playwright uses to render ECharts plots.
RUN uv run playwright install chromium

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
