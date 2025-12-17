#!/usr/bin/env python3
"""
Script zum manuellen Hochladen von gespeicherten Scan-PDFs vom Pi.
Verwendung: python upload_pending_scans.py <pdf_path> <session_id>
"""

import sys
import os
import requests
from pathlib import Path

# Django Setup
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdorm.settings')

import django
django.setup()

from smartdorm.models import PrintSession

def upload_scan(pdf_path: str, session_id: str):
    """Lädt ein Scan-PDF hoch und ordnet es einer Session zu."""
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ Datei nicht gefunden: {pdf_path}")
        return False
    
    # Session prüfen
    try:
        session = PrintSession.objects.get(external_id=session_id)
    except PrintSession.DoesNotExist:
        print(f"❌ Session nicht gefunden: {session_id}")
        return False
    
    # Upload-URL (lokal)
    upload_url = "http://localhost:8000/api/printing/scans/"
    
    try:
        with open(pdf_file, 'rb') as f:
            files = {'file': (pdf_file.name, f, 'application/pdf')}
            data = {'session_id': session_id}
            
            print(f"📤 Lade {pdf_file.name} hoch für Session {session_id}...")
            response = requests.post(upload_url, files=files, data=data, timeout=30)
        
        if response.status_code == 201:
            result = response.json()
            scan_id = result.get('external_id', 'unknown')
            print(f"✅ Upload erfolgreich! Scan-ID: {scan_id}")
            
            # PDF löschen nach erfolgreichem Upload
            pdf_file.unlink()
            print(f"🗑️  PDF gelöscht: {pdf_file}")
            return True
        else:
            print(f"❌ Upload fehlgeschlagen: {response.status_code}")
            print(f"   Antwort: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Fehler beim Upload: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Verwendung: python upload_pending_scans.py <pdf_path> <session_id>")
        print("\nBeispiel:")
        print("  python upload_pending_scans.py /tmp/smartdorm_scans/pending_xxx_scan.pdf e1c090de93384bacba049ef8f07714b4")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    session_id = sys.argv[2]
    
    upload_scan(pdf_path, session_id)

