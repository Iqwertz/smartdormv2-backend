#!/bin/bash

# Smart Dorm Backend Test Script

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

# Run the tests
echo "Running Django tests..."
python manage.py test smartdorm.tests.integration.test_api 