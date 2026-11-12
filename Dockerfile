FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install curl for container health checks and GTK/Pango runtime libs for WeasyPrint PDF generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    fontconfig \
    fonts-dejavu-core \
    libffi8 \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging configuration first for Docker layer caching
COPY pyproject.toml .

# Install dependencies without pip cache to minimize image size and memory footprint
RUN pip install --no-cache-dir .

# Copy application code, database migrations, and assets
COPY alembic.ini .
COPY alembic alembic
COPY app app
COPY scripts scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
