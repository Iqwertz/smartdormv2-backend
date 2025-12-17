#!/usr/bin/env python3
"""
SmartDorm Scan Service für Raspberry Pi
HTTP-Service der Scan-Befehle von SmartDorm empfängt und scanimage ausführt.

Installation auf Pi:
1. Kopiere diese Datei nach /srv/smartdorm/scan_service.py
2. Installiere Dependencies: pip install flask requests
3. Erstelle Systemd-Service (siehe unten)
4. Starte Service: sudo systemctl start smartdorm-scan-service
"""

import os
import sys
import subprocess
import tempfile
import shutil
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
import requests

# Logging konfigurieren (für systemd)
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ⚠️ KONFIGURATION: Anpassen!
SMARTDORM_API_BASE = os.environ.get(
    "SMARTDORM_API_BASE",
    "http://smartdormv2-api-dev.schollheim.net/api"  # DEV
)
SCAN_DEVICE = os.environ.get(
    "SCAN_DEVICE",
    "airscan:w0:Samsung C1860 Series (SEC8425192A15C2)"  # WSD/AirScan Device (vollständiger Name)
)
SCAN_TEMP_DIR = Path("/tmp/smartdorm_scans")
SCAN_TEMP_DIR.mkdir(exist_ok=True, mode=0o755)


def scan_to_pdf(resolution=300, mode="Color", source="Flatbed"):
    """
    Führt Scan aus und gibt PDF-Pfad zurück.
    
    Args:
        resolution: DPI (75, 100, 150, 200, 300, 600)
        mode: "Color" oder "Gray"
        source: "Flatbed" oder "ADF"
    
    Returns:
        Path zu erstelltem PDF oder None bei Fehler
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tiff_path = SCAN_TEMP_DIR / f"scan_{timestamp}.tiff"
    pdf_path = SCAN_TEMP_DIR / f"scan_{timestamp}.pdf"
    
    try:
        # Scan-Kommando zusammenstellen
        cmd = [
            "scanimage",
            "-d", SCAN_DEVICE,
            "--mode", mode,
            "--resolution", str(resolution),
            "--format=tiff",
            f"--source={source}"
        ]
        
        logger.info(f"[SCAN] Ausführe: {' '.join(cmd)}")
        sys.stdout.flush()
        
        # Scan ausführen
        with open(tiff_path, 'wb') as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=300  # 5 Minuten Timeout
            )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"[SCAN] Fehler (Returncode {result.returncode}): {error_msg}")
            sys.stderr.flush()
            if tiff_path.exists():
                tiff_path.unlink()
            return None
        
        if not tiff_path.exists() or tiff_path.stat().st_size == 0:
            logger.error(f"[SCAN] Fehler: TIFF-Datei leer oder nicht erstellt")
            sys.stderr.flush()
            return None
        
        logger.info(f"[SCAN] TIFF erstellt: {tiff_path} ({tiff_path.stat().st_size} Bytes)")
        sys.stdout.flush()
        
        # TIFF zu PDF konvertieren
        convert_cmd = ["tiff2pdf", str(tiff_path), "-o", str(pdf_path)]
        logger.info(f"[SCAN] Konvertiere: {' '.join(convert_cmd)}")
        sys.stdout.flush()
        
        result = subprocess.run(
            convert_cmd,
            stderr=subprocess.PIPE,
            timeout=60
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"[SCAN] Konvertierungs-Fehler (Returncode {result.returncode}): {error_msg}")
            sys.stderr.flush()
            if tiff_path.exists():
                tiff_path.unlink()
            return None
        
        if not pdf_path.exists():
            logger.error(f"[SCAN] Fehler: PDF nicht erstellt")
            sys.stderr.flush()
            if tiff_path.exists():
                tiff_path.unlink()
            return None
        
        logger.info(f"[SCAN] PDF erstellt: {pdf_path} ({pdf_path.stat().st_size} Bytes)")
        sys.stdout.flush()
        
        # TIFF löschen (nur PDF behalten)
        if tiff_path.exists():
            tiff_path.unlink()
        
        return pdf_path
        
    except subprocess.TimeoutExpired:
        logger.error(f"[SCAN] Timeout beim Scannen")
        sys.stderr.flush()
        if tiff_path.exists():
            tiff_path.unlink()
        return None
    except Exception as e:
        logger.error(f"[SCAN] Unerwarteter Fehler: {e}", exc_info=True)
        sys.stderr.flush()
        if tiff_path.exists():
            tiff_path.unlink()
        if pdf_path.exists():
            pdf_path.unlink()
        return None


@app.route('/scan/start', methods=['POST'])
def start_scan():
    """
    POST /scan/start
    Startet einen Scan und lädt das PDF zu SmartDorm hoch.
    
    Request Body:
        {
            "session_id": "abc123",
            "resolution": 300,
            "mode": "Color",
            "source": "Flatbed"
        }
    
    Response:
        {
            "scan_id": "...",
            "status": "completed" | "failed",
            "message": "..."
        }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        resolution = data.get('resolution', 300)
        mode = data.get('mode', 'Color')
        source = data.get('source', 'Flatbed')
        
        if not session_id:
            return jsonify({"error": "session_id required"}), 400
        
        logger.info(f"[API] Scan-Request erhalten: session={session_id}, resolution={resolution}, mode={mode}, source={source}")
        sys.stdout.flush()
        
        # Scan ausführen
        try:
            pdf_path = scan_to_pdf(resolution=resolution, mode=mode, source=source)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[API] Scan-Fehler: {error_msg}", exc_info=True)
            sys.stderr.flush()
            return jsonify({
                "scan_id": None,
                "status": "failed",
                "message": f"Scan-Fehler: {error_msg}"
            }), 500
        
        if not pdf_path:
            logger.error(f"[API] Scan fehlgeschlagen: pdf_path ist None")
            sys.stderr.flush()
            return jsonify({
                "scan_id": None,
                "status": "failed",
                "message": "Scan fehlgeschlagen - siehe Pi-Logs für Details"
            }), 500
        
        # PDF zu SmartDorm hochladen
        upload_url = f"{SMARTDORM_API_BASE}/printing/scans/"
        
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': (pdf_path.name, f, 'application/pdf')}
                data_upload = {'session_id': session_id}
                
                logger.info(f"[API] Lade PDF hoch zu: {upload_url}")
                sys.stdout.flush()
                
                upload_resp = requests.post(
                    upload_url,
                    files=files,
                    data=data_upload,
                    timeout=30
                )
            
            if upload_resp.status_code == 201:
                response_data = upload_resp.json()
                scan_id = response_data.get('external_id', 'unknown')
                
                logger.info(f"[API] Upload erfolgreich: scan_id={scan_id}")
                sys.stdout.flush()
                
                # PDF löschen (wurde zu SmartDorm hochgeladen)
                if pdf_path.exists():
                    pdf_path.unlink()
                
                return jsonify({
                    "scan_id": scan_id,
                    "status": "completed",
                    "message": "Scan erfolgreich hochgeladen"
                }), 200
            else:
                logger.error(f"[API] Upload fehlgeschlagen: {upload_resp.status_code} - {upload_resp.text}")
                sys.stderr.flush()
                
                # PDF behalten für manuelle Übertragung
                saved_path = SCAN_TEMP_DIR / f"pending_{session_id}_{pdf_path.name}"
                pdf_path.rename(saved_path)
                logger.warning(f"[API] PDF gespeichert für späteren Upload: {saved_path}")
                
                return jsonify({
                    "scan_id": None,
                    "status": "failed",
                    "message": f"Upload fehlgeschlagen: {upload_resp.status_code}. PDF gespeichert unter {saved_path}"
                }), 502
                
        except requests.exceptions.RequestException as e:
            logger.error(f"[API] Netzwerk-Fehler beim Upload: {e}", exc_info=True)
            sys.stderr.flush()
            
            # PDF für späteren Upload speichern
            saved_path = SCAN_TEMP_DIR / f"pending_{session_id}_{pdf_path.name}"
            try:
                pdf_path.rename(saved_path)
                logger.warning(f"[API] PDF gespeichert für späteren Upload (Netzwerk-Fehler): {saved_path}")
            except Exception as rename_error:
                logger.error(f"[API] Konnte PDF nicht umbenennen: {rename_error}")
            
            return jsonify({
                "scan_id": None,
                "status": "failed",
                "message": f"Netzwerk-Fehler: Backend nicht erreichbar. PDF gespeichert unter {saved_path}. Bitte später manuell hochladen."
            }), 502
        finally:
            # Cleanup: Alte Dateien löschen (älter als 1 Stunde)
            try:
                for file in SCAN_TEMP_DIR.glob("scan_*.pdf"):
                    if file.stat().st_mtime < (datetime.now().timestamp() - 3600):
                        file.unlink()
            except Exception:
                pass
        
    except Exception as e:
        logger.error(f"[API] Unerwarteter Fehler: {e}", exc_info=True)
        sys.stderr.flush()
        return jsonify({
            "scan_id": None,
            "status": "failed",
            "message": f"Fehler: {str(e)}"
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health-Check Endpoint"""
    return jsonify({
        "status": "ok",
        "service": "smartdorm-scan-service",
        "device": SCAN_DEVICE
    }), 200


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("SmartDorm Scan Service")
    logger.info("=" * 60)
    logger.info(f"API: {SMARTDORM_API_BASE}")
    logger.info(f"Device: {SCAN_DEVICE}")
    logger.info(f"Temp Dir: {SCAN_TEMP_DIR}")
    logger.info("=" * 60)
    sys.stdout.flush()
    
    # Entwicklungs-Server (für Tests)
    # Produktiv: Nutze systemd + gunicorn
    app.run(host='0.0.0.0', port=8000, debug=False)

