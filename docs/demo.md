# SmartDorm Demo Environment

To demonstrate the capabiilities of SmartDorm to external people, without exposing sensible data from the production database or live LDAP servers, this repository includes a self-contained, containerized demo environment. It is not meant for testing but just to deploy it on a vps to demo the application to external people without exposing production secrets.

## Overview

The demo environment is orchestrated using Docker Compose (`docker-compose.demo.yml`). It sets up a complete, mock infrastructure that accurately simulates the production environment:

1. **Django Backend Server**: Runs the application locally using Gunicorn.
2. **PostgreSQL Database**: A local PostgreSQL instance specifically for demo data.
3. **Redis**: Used for session caching.
4. **Mock OpenLDAP Server**: A lightweight, tailored Alpine-based LDAP server seeded with dummy authentication data.

## Features

- **No Production Dependencies**: Fully isolated. It does not require real environment secrets, the production database, or the production LDAP server.
- **Dynamic Schema Generation**: During the image build, Django models (which are normally `managed = False` mapped to a legacy DB) are automatically patched to `managed = True`. A fresh set of migrations is generated and applied to the fresh mock database, solving schema mismatches.
- **Comprehensive Dummy Data**: The `generate_demo_data.py` script automatically seeds the database on startup right after migrations. It generates realistic fake data including:
  - 600+ Mock Tenants
  - Fake Rooms, Departments, and Subtenants
  - Dummy Engagements, Claims, and Deposit Bank information
- **Mock Authentication**: The LDAP server contains an admin user with maximum privileges natively mapped to the `ADMIN` group.

## How to Run

1. Make sure you have Docker and Docker Compose installed.
2. In the root of the backend repository, run the following command:
   ```bash
   docker compose -f docker-compose.demo.yml up -d --build
   ```
3. The containers will build and start. Wait about 10-20 seconds during the first boot for the database migrations and data generation to finish.
4. The API will be available at `http://localhost:8000`.

## Demo Credentials

You can test LDAP login routes or any authenticated endpoints using the seeded credentials:

- **Username**: `admin`
- **Password**: `admin`
- **Permissions**: This user acts as a global administrator.

## Stopping the Demo

To stop the demo and completely wipe the demo database volume, you can run:
```bash
docker compose -f docker-compose.demo.yml down -v
```
