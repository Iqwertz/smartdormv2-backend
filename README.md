# SmartDorm Backend

Django-based backend for the SmartDorm dormitory management system.
A overview documentation (Mostly AI generated, but checked for accuracy) is in the /docs folder.

## Quick Start


### Using venv
It is recommended to use pyvenv for the project:
To install pyvenv:
```bash	
curl -fsSL https://pyenv.run | bash
```
Then, run the following command to install the dependencies:
```bash
pyenv install
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Finally create `.env` file: `cp .sample.env .env` and fill with secrets from vault

## Redis Server for Session Tokens

Redis is used to store user sessions, enabling persistent logins ("Remember Me").

### Installation

```bash
sudo apt-get update
sudo apt-get install redis-server
```

### Start Redis Server

```bash
sudo service redis-server start
```

### Add Redis to Autostart

```bash
sudo systemctl enable redis-server
```

### Run
1. Run server: `./run-server.sh`
2. Run tests: `./run-tests.sh`

## Demo Environment (Docker)

To demonstrate the system to external people, a fully self-contained Docker environment is available. It creates a mock PostgreSQL database, mock Redis, a mock custom OpenLDAP server, and automatically seeds comprehensive realistic fake data without touching production configurations.

Please view [docs/demo.md](docs/demo.md) for detailed instructions on starting and using the demo environment.

## Tenant API Demo

Run `scripts/tenant_api_demo.py` script using:

```bash
source .env
python scripts/tenant_api_demo.py
```

This demo:
- Creates a test tenant via API POST request
- Retrieves all tenants to verify addition
- Deletes the test tenant via API DELETE request

## Tenant Statistics Recalculation

There is a management command designed to ensure data consistency for tenant statistics (Points, Sublet duration, Extensions). This routine runs automatically every night at 04:00 AM via a cron job set up during deployment.

It performs the following recalculations for **current tenants only**:
1. **Points:** Recalculates based on the sum of points from all *compensated* engagements.
2. **Sublet Duration:** Calculates the total days of all *confirmed* subtenants, converts to months (30 days = 1 month), and rounds to the nearest 0.5 months.
3. **Extensions:** Recalculates based on the count of *approved* extension claims.

Any discrepancies found are updated in the database and logged to `logs/smartdorm.log`.

### Manual Trigger
To run this routine manually:
```bash
python manage.py recalculate_tenant_stats
```

## LDAP commands useful for testing
Get all user attributes:
```bash
ldapsearch -x -LLL \
  -H ldap://ldap.schollheim.net:389 \
  -D "cn=admin,dc=schollheim,dc=net" -W \
  -b "dc=schollheim,dc=net" \
  "(cn=username)" \
  \* +
```
List all available Groups:
```bash
ldapsearch -x -LLL -b "ou=groups2,dc=schollheim,dc=net" -D "cn=admin,dc=schollheim,dc=net" -W "(objectClass=groupOfNames)" cn -H ldap://ldap.schollheim.net:389
```