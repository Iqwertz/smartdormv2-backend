#!/usr/bin/env python3
"""
Script zum Anzeigen aller Tenants in der DB
"""
import os
import sys
from pathlib import Path
import django

def load_env_file():
    """Lädt .env Datei vor Django-Setup"""
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"

    if not env_path.exists():
        return

    with env_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value

load_env_file()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdorm.settings')
django.setup()

from smartdorm.models import Tenant

def main():
    print("=" * 60)
    print("Tenants in der Datenbank:")
    print("=" * 60)
    
    tenants = Tenant.objects.filter(username__isnull=False).exclude(username='')[:20]
    
    if tenants.count() == 0:
        print("❌ Keine Tenants mit Username gefunden!")
        return
    
    print(f"\nAnzahl: {tenants.count()}\n")
    
    for tenant in tenants:
        print(f"Username: {tenant.username}")
        print(f"  Name: {tenant.name} {tenant.surname}")
        print(f"  Email: {tenant.email}")
        print(f"  Zimmer: {tenant.current_room or 'N/A'}")
        print()

if __name__ == '__main__':
    main()

