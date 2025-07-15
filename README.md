# SmartDorm Backend

Django-based backend for the SmartDorm dormitory management system.

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

## Tenant API Demo

Run `scripts/tenant_api_demo.py` script using:

```bash
python scripts/tenant_api_demo.py
```

This demo:
- Creates a test tenant via API POST request
- Retrieves all tenants to verify addition
- Deletes the test tenant via API DELETE request

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
