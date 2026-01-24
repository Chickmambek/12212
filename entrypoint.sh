#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Navigate to the inner project directory where manage.py is located
cd bookmaker

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Django Q cluster in the background
echo "Starting Django Q cluster..."
python manage.py qcluster &

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn bookmaker.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
