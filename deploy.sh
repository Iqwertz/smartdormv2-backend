#!/bin/bash
#Deploy script for CI/CD pipeline on the vms. Dont execute this script locally
set -e # Exit immediately if a command exits with a non-zero status.

BRANCH_NAME=${1} # Accept the branch name as the first argument

if [ -z "$BRANCH_NAME" ]; then
    echo "Error: Branch name not provided."
    exit 1
fi

echo "Starting deployment for branch: ${BRANCH_NAME}..."

# Navigate to the project directory
cd /var/www/smartdorm/smartdormv2-backend

# Fetch all remote changes and switch to the correct branch
git fetch origin
git checkout ${BRANCH_NAME}

# Pull the latest changes for that specific branch
git pull origin ${BRANCH_NAME}

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
source venv/bin/activate

echo "Ensuring logs directory exists..."
mkdir -p logs

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run database migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files for Nginx
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Deactivate the virtual environment
deactivate

echo "Deployment finished. Restarting Gunicorn service..."

# Restart the Gunicorn service
sudo systemctl restart gunicorn

echo "Gunicorn restarted. Deployment for ${BRANCH_NAME} complete."