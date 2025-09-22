#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Execute the main container command (e.g., uvicorn)
echo "Starting application..."
exec "$@"

