# Driver-Hub Matching Service Dockerfile
# Multi-stage build for a lightweight serverless-ready container

# Build stage
FROM python:3.10-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST="0.0.0.0" \
    WORKERS=1

# Copy application code
COPY app/ ./app/
COPY data/ ./data/
COPY .env.example ./.env.example
COPY README.md ./README.md

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser
USER appuser

# Expose port
EXPOSE 8000

# Command to run the application
# Using Gunicorn with Uvicorn workers for production
CMD exec gunicorn --bind $HOST:$PORT --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker --timeout 120 --graceful-timeout 30 app.main:app
