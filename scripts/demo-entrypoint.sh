#!/bin/bash

echo "Waiting for postgres..."
while ! nc -z db 5432 >/dev/null 2>&1; do
  sleep 0.5
done
echo "PostgreSQL started"

echo "Waiting for redis..."
while ! nc -z redis 6379 >/dev/null 2>&1; do
  sleep 0.5
done
echo "Redis started"

echo "Waiting for ldap..."
while ! nc -z ldap 389 >/dev/null 2>&1; do
  sleep 0.5
done
echo "LDAP started"

set -e

# Set marker for demo setup in case scripts check
export DEMO_MODE=true

echo "Creating fresh migrations for demo schema..."
python manage.py makemigrations smartdorm

echo "Running migrations..."
python manage.py migrate --noinput

echo "Generating demo data..."
python manage.py generate_demo_data

echo "Starting Gunicorn server..."
exec gunicorn smartdorm.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2
