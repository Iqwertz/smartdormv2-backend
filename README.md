# SmartDorm Backend

Django-based backend for the SmartDorm dormitory management system.

## Quick Start

1. Create `.env` file: `cp .sample.env .env` and fill with secrets from vault
2. Install dependencies: `pip install -r requirements.txt`
3. Run server: `./run-server.sh`
4. Run tests: `./run-tests.sh`

## Tenant API Demo

Run `scripts/tenant_api_demo.py` script using:

```
python scripts/tenant_api_demo.py
```

This demo:
- Creates a test tenant via API POST request
- Retrieves all tenants to verify addition
- Deletes the test tenant via API DELETE request