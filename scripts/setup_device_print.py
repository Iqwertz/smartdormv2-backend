#!/usr/bin/env python3
"""
Create or reset the SmartDorm print Device in the database.

- Loads .env from the backend directory (same as run-server.sh).
- Deletes existing Device(s), then creates one with default values.
- Requires at least one Department to exist.

Usage (from backend root):
    python scripts/setup_device_print.py
"""
import os
import sys
from pathlib import Path

import django

# Defaults for the new device (adjust if needed)
DEVICE_NAME = "Samsung Xpress C1860FW"
DEVICE_LOCATION = "Creative Department Room"
CUPS_PRINTER_NAME = "Samsung_C1860_Series"
PRICE_COLOR = "0.10"
PRICE_GRAY = "0.05"
MAX_SESSION_MINUTES = 30


def load_env():
    """Load KEY=VALUE from backend .env into os.environ (skip if already set)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"").strip()
        if key and value and key not in os.environ:
            os.environ[key] = value


def main():
    load_env()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartdorm.settings")
    django.setup()

    from decimal import Decimal
    from smartdorm.models import Device, Department

    count = Device.objects.count()
    print(f"Current devices: {count}")
    if count > 0:
        for d in Device.objects.all():
            print(f"  - {d.id}: {d.name} ({d.location})")
        Device.objects.all().delete()
        print("All devices removed.")

    department = Department.objects.first()
    if not department:
        print("Error: No department in database. Create one first.")
        sys.exit(1)

    device = Device.objects.create(
        name=DEVICE_NAME,
        location=DEVICE_LOCATION,
        department=department,
        is_active=True,
        allow_new_sessions=True,
        price_per_page_color=Decimal(PRICE_COLOR),
        price_per_page_gray=Decimal(PRICE_GRAY),
        max_session_duration_minutes=MAX_SESSION_MINUTES,
        cups_printer_name=CUPS_PRINTER_NAME,
    )
    print(f"Device created: id={device.id}, name={device.name}, cups={device.cups_printer_name}")


if __name__ == "__main__":
    main()
