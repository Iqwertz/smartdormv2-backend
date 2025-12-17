#!/usr/bin/env python3
"""
Script zum Löschen und Neu-Erstellen des Print-Devices.

Hinweis:
- Lädt Variablen aus der .env-Datei im Backend-Verzeichnis,
  damit dieselben DB-Einstellungen wie im run-server.sh verwendet werden.
"""
import os
import sys
from pathlib import Path

import django


def load_env_file():
    """
    Lädt einfache KEY=VALUE oder export KEY=VALUE Einträge aus .env
    und setzt sie in os.environ, bevor Django initialisiert wird.
    """
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"

    if not env_path.exists():
        return

    with env_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Optionales "export " entfernen
            if line.startswith("export "):
                line = line[len("export ") :]
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


def django_setup():
    """
    Führt das Django-Setup mit geladenen Umgebungsvariablen aus.
    """
    # Basisverzeichnis für Django hinzufügen
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartdorm.settings")
    django.setup()


def main():
    # .env laden und Django initialisieren
    load_env_file()
    django_setup()

    from smartdorm.models import Device, Department

    # Prüfe aktuelle Devices
    devices = Device.objects.all()
    count = devices.count()
    
    print(f"Vorher: {count} Device(s) gefunden")
    
    if count > 0:
        for device in devices:
            print(f"  - ID: {device.id}, Name: {device.name}, Location: {device.location}")
        
        # Lösche alle
        Device.objects.all().delete()
        print(f"\n✅ Alle Devices gelöscht!")
        print(f"Nachher: {Device.objects.count()} Device(s)")
    else:
        print("Keine Devices zum Löschen gefunden.")
    
    # Hole ein Referat
    department = Department.objects.first()
    if not department:
        print("\n❌ FEHLER: Kein Referat in der Datenbank gefunden!")
        print("Bitte zuerst ein Referat in der DB anlegen.")
        return
    
    print(f"\nVerwende Referat: {department.name} ({department.full_name})")
    
    # Erstelle neues Device
    device = Device.objects.create(
        name="Samsung Xpress C1860FW",
        location="Kreativreferat Zimmer",
        department=department,
        is_active=True,
        allow_new_sessions=True,
        price_per_page=0.10,
        max_session_duration_minutes=30,
        cups_printer_name="Samsung_C1860_Series"
    )
    
    print(f"\n✅ Device erfolgreich erstellt:")
    print(f"   ID: {device.id}")
    print(f"   Name: {device.name}")
    print(f"   Location: {device.location}")
    print(f"   Referat: {device.department.name}")
    print(f"   CUPS Name: {device.cups_printer_name}")

if __name__ == '__main__':
    main()

