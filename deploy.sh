#!/bin/bash
# Deploy script for CI/CD pipeline on the vms.
# This script is executed after rsync has copied the new code.
set -e # Exit immediately if a command exits with a non-zero status.

echo "Starting post-sync deployment tasks..."

# Navigate to the project directory
cd /var/www/smartdorm/smartdormv2-backend

# Load environment variables from .env file
if [ -f .env ]; then
  set -a
  source .env
  set +a
else
  echo "Error: .env file not found"
  exit 1
fi

# Activate the virtual environment
python3 -m venv venv
source venv/bin/activate

echo "Ensuring logs directory exists..."
mkdir -p logs

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
pip install gunicorn

# Run database migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files for Nginx
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Deactivate the virtual environment
deactivate

# echo "Setting file permissions..."
# sudo chown -R www-data:www-data /var/www/smartdorm/smartdormv2-backend

echo "Deployment finished. Restarting Gunicorn service..."

# Restart the Gunicorn service
sudo systemctl restart gunicorn

echo "Gunicorn restarted. Deployment complete."