#!/bin/bash

# Smart Dorm Backend Server Script

# Load environment variables from .env file
if [ -f .env ]; then
  source .env
else
  echo "Error: .env file not found"
  exit 1
fi

# Export environment variables for Django
export DB_PASSWORD
export PGPASSWORD="${DB_PASSWORD}"

# Check database connection
echo "Checking database connection..."
if ! psql -h "${DB_HOST}" -U "${POSTGRES_USER}" -p "${DB_PORT}" -d "${POSTGRES_DB}" -c "SELECT 1" > /dev/null 2>&1; then
    echo "Error: Could not connect to database. Please check your connection settings."
    exit 1
fi
echo "Database connection successful."

# Run Django migrations
echo "Running Django migrations..."
python manage.py makemigrations
python manage.py migrate

# Start the Django development server
echo "Starting Django development server..."
python manage.py runserver 0.0.0.0:8000
