#!/bin/bash


# Set default test type if not provided
TEST_TYPE="${TEST_TYPE:-all}"

# Load environment variables from .env file
if [ -f .env ]; then
  source .env
else
  echo "Error: .env file not found"
  exit 1
fi

export DB_PASSWORD
export PGPASSWORD="${DB_PASSWORD}"

if [ "$TEST_TYPE" = "unit" ]; then
  echo "Running Django unit tests only..."
  python manage.py test smartdorm.tests.unit
else
  echo "Running all Django tests..."
  python manage.py test smartdorm.tests
fi 