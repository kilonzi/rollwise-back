# syntax=docker/dockerfile:1
FROM python:3.11-slim as base

# Security: non-root user
RUN useradd -m appuser

WORKDIR /app

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Set environment variables for production
ENV PYTHONUNBUFFERED=1 \
    PORT=8080

# Use non-root user
USER appuser

# Expose port for Cloud Run
EXPOSE 8080

# Entrypoint for Cloud Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

