# ==============================================================================
# The Lenny Growth Assistant - Backend Container Dockerfile
# Optimized for Python 3.11 asynchronous FastAPI runtime with pgvector & SQLAlchemy
# ==============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies: curl for healthchecks and build essentials for wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for layer caching
COPY backend/requirements.txt /app/backend/requirements.txt

# Install Python backend dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend application source code and ingestion modules
COPY backend /app/backend
COPY ingestion /app/ingestion

# Copy entrypoint script and ensure execute permissions
COPY docker/backend-entrypoint.sh /app/backend-entrypoint.sh
RUN chmod +x /app/backend-entrypoint.sh

# Environment variables
ENV PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Healthcheck targeting FastAPI liveness endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

ENTRYPOINT ["/app/backend-entrypoint.sh"]
