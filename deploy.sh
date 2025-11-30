#!/bin/bash
# Deploy script for CI/CD pipeline on the vms.
# This script is executed after rsync has copied the new code.
set -e # Exit immediately if a command exits with a non-zero status.

echo "Starting post-sync deployment tasks..."

PROJECT_DIR="/var/www/smartdorm/smartdormv2-backend"
VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"
MANAGE_PY="${PROJECT_DIR}/manage.py"
LOG_DIR="${PROJECT_DIR}/logs"

# Navigate to the project directory
cd "${PROJECT_DIR}"

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
mkdir -p "${LOG_DIR}"

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

# Cronjob Management for Nightly Recalculation
echo "Configuring nightly recalculation cronjob..."

# Run at 04:00 AM every day
CRON_CMD="0 4 * * * cd ${PROJECT_DIR} && set -a && source .env && set +a && ${VENV_PYTHON} ${MANAGE_PY} recalculate_tenant_stats >> ${LOG_DIR}/cron.log 2>&1"

# 1. Dump current crontab
# 2. Grep -v removes any existing lines containing 'recalculate_tenant_stats' (cleanup old jobs)
# 3. Append the new command
# 4. Pipe into crontab to update
(crontab -l 2>/dev/null | grep -v "recalculate_tenant_stats" || true; echo "$CRON_CMD") | crontab -

echo "Cronjob updated successfully."

# Deactivate the virtual environment
deactivate

# echo "Setting file permissions..."
# sudo chown -R www-data:www-data /var/www/smartdorm/smartdormv2-backend

echo "Deployment finished. Restarting Gunicorn service..."

# Restart the Gunicorn service
sudo systemctl restart gunicorn

echo "Gunicorn restarted. Deployment complete."