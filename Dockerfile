FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
