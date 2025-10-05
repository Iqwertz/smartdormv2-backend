#!/bin/bash

# Smart Dorm Backend Server Script

#Redis check
echo "Checking Redis connection..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Error: Redis server is not responding on localhost:6379."
    echo "Please ensure Redis is installed and running."
    echo " - On Linux: sudo systemctl start redis-server"
    echo " - On WSL2: sudo service redis-server start"
    echo " - On macOS: brew services start redis"
    return
fi
echo "Redis connection successful."

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
echo "psql -h ${DB_HOST} -U ${POSTGRES_USER} -p ${DB_PORT} -d ${POSTGRES_DB} -c 'SELECT 1'"
echo "Checking database connection..."
if ! psql -h "${DB_HOST}" -U "${POSTGRES_USER}" -p "${DB_PORT}" -d "${POSTGRES_DB}" -c "SELECT 1" > /dev/null 2>&1; then
    echo "Error: Could not connect to database. Please check your connection settings."
    return
fi
echo "Database connection successful."

echo "Creating logs folder if it does not exist..."
# Create logs directory if it doesn't exist
mkdir -p logs


# Run Django migrations
echo "Running Django migrations..."
python manage.py makemigrations
python manage.py makemigrations smartdorm
python manage.py migrate
python manage.py migrate smartdorm

# Start the Django development server
echo "Starting Django development server..."
python manage.py runserver 0.0.0.0:8000
