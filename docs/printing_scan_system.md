# Druck- und Scan-Abrechnungssystem in SmartDorm

## Überblick

SmartDorm wird um ein Druck- und Scan-Feature erweitert, das in Zusammenarbeit mit einem Raspberry Pi Druckserver (Linux, CUPS) und einem Samsung Xpress C1860FW Multifunktionsdrucker funktioniert. Das System ermöglicht es Bewohnern, Dokumente über SmartDorm zu drucken und zu scannen, während Druckkosten automatisch erfasst und zugeordnet werden.

**Stand:** Planungsphase - Keine Implementierung erfolgt

---

## Funktionsbeschreibung und Anforderungen

### Ziel 1 – Druckjobs über SmartDorm auslösen und abrechnen

- Dokumente werden in SmartDorm hochgeladen (PDF, idealerweise weitere Office-Formate später)
- SmartDorm sendet einen Printjob an den Raspberry Pi (CUPS)
- CUPS schickt den Druckauftrag an den Drucker
- SmartDorm erkennt, ob ein Druck erfolgreich oder fehlgeschlagen ist
- Erfolgreiche Seiten werden pro Nutzer abgerechnet
- Test-Case: Eine Session, in der mehrere Dokumente nacheinander gedruckt werden können

### Ziel 2 – Scannen mit Zuordnung zum eingeloggten Nutzer

- Der Nutzer muss im SmartDorm UI eine aktive Session starten
- Während einer Session ist klar, welcher Nutzer am Gerät steht
- Der Drucker sendet Scans an den Pi (z. B. per "Scan to PC" / SMB / FTP)
- Der Pi ordnet eingegangene Dokumente der aktuell aktiven Session zu
- SmartDorm speichert diese gescannten Dokumente
- Optionen: in SmartDorm direkt anzeigen, oder automatisierte Weiterleitungen (Mail, Cloud)
- Scans erzeugen KEINE Kosten, sollen aber pro Nutzer geloggt werden

### Ziel 3 – Kopieren ist deaktiviert

- Kopieren am Gerät ist vorerst technisch deaktiviert
- Grund: Kopierjobs sind offline und nicht trackbar, daher nicht abrechenbar
- Optional: später SNMP Page Counter nutzen, um Kopierkosten indirekt zu erfassen (nicht im MVP)

---

## Session-Logik (zentrales Feature)

### Grundregeln

- Ein Nutzer kann nur eine aktive Session gleichzeitig haben
- Während aktiver Session wird im UI angezeigt:
  - Gerät = "Verfügbar" oder "Belegt von: Nutzername"
- Wird eine Session gestartet:
  - Drucker wird freigeschaltet (kein Power-Control, nur Software-Access)
  - Scans werden dem Session-User zugeordnet
  - Druckjobs sind nur für diesen Nutzer erlaubt
- Session kann ablaufen oder manuell beendet werden:
  - Nach Session wird Gerät wieder frei
  - Falls Scans/Druckjobs im Transit waren → Status sensible behandeln

### Session-Status

- `ACTIVE`: Session läuft, Nutzer kann drucken/scannen
- `COMPLETED`: Session wurde normal beendet
- `EXPIRED`: Session ist abgelaufen (Timeout)
- `TERMINATED`: Session wurde von Admin/Referat beendet

---

## Kostenmodell (MVP)

- Kosten werden nur durch Druckseiten erzeugt
- Speicherung in SmartDorm:
  - Benutzer
  - Datum/Uhrzeit
  - Anzahl Seiten
  - Status (erfolgreich, fehlgeschlagen → keine Kosten)
- Abzüge von möglichem Guthaben (optional später)
- Preismodell konfigurierbar (z. B. €/Seite)

---

## Datenmodell

### Device (Drucker/Scanner)

```python
class Device(models.Model):
    """Repräsentiert einen Drucker/Scanner"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)  # z.B. "Samsung Xpress C1860FW"
    location = models.CharField(max_length=255)  # z.B. "Kreativreferat Zimmer"
    department = models.ForeignKey(Department, on_delete=models.PROTECT)  # Verantwortliches Referat
    is_active = models.BooleanField(default=True)  # Global ein/aus
    allow_new_sessions = models.BooleanField(default=True)  # Neue Sessions erlauben
    price_per_page = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.10'))
    max_session_duration_minutes = models.IntegerField(default=30)
    cups_printer_name = models.CharField(max_length=255)  # CUPS-Printer-Name
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 't_device'
```

### PrintSession (Session-Management)

```python
class PrintSession(models.Model):
    """Aktive oder vergangene Druck-/Scan-Sessions"""
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Aktiv'
        COMPLETED = 'COMPLETED', 'Abgeschlossen'
        EXPIRED = 'EXPIRED', 'Abgelaufen'
        TERMINATED = 'TERMINATED', 'Beendet'
    
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    external_id = models.CharField(max_length=255, unique=True)  # UUID
    
    class Meta:
        db_table = 't_print_session'
```

### PrintJob (Druckaufträge)

```python
class PrintJob(models.Model):
    """Einzelne Druckaufträge"""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Wartend'
        PRINTING = 'PRINTING', 'Druckt'
        COMPLETED = 'COMPLETED', 'Erfolgreich'
        FAILED = 'FAILED', 'Fehlgeschlagen'
        CANCELLED = 'CANCELLED', 'Abgebrochen'
    
    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(PrintSession, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    pages = models.IntegerField(null=True, blank=True)  # Wird nach Druck aktualisiert
    cost = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    cups_job_id = models.CharField(max_length=255, null=True, blank=True)  # CUPS Job ID
    external_id = models.CharField(max_length=255, unique=True)  # UUID
    
    class Meta:
        db_table = 't_print_job'
```

### Scan (Gescannte Dokumente)

```python
class Scan(models.Model):
    """Gescannte Dokumente"""
    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(PrintSession, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)  # Pfad zum gescannten File
    scanned_at = models.DateTimeField(auto_now_add=True)
    external_id = models.CharField(max_length=255, unique=True)  # UUID
    
    class Meta:
        db_table = 't_scan'
```

---

## User Interface - Tenant Ansicht

### Hauptseite: `/print`

#### Layout (wenn keine Session aktiv):

```
┌─────────────────────────────────────────┐
│  Drucken & Scannen                      │
├─────────────────────────────────────────┤
│                                         │
│  📊 DRUCKERSTATUS                       │
│  ┌─────────────────────────────────┐   │
│  │ Status: Verfügbar / Belegt      │   │
│  │ Aktive Session: Max Mustermann   │   │
│  │ Toner: 85% | Papier: ✓          │   │
│  └─────────────────────────────────┘   │
│                                         │
│  💰 KOSTENÜBERSICHT                    │
│  ┌─────────────────────────────────┐   │
│  │ Diesen Monat: 45 Seiten         │   │
│  │ Kosten: €4.50                   │   │
│  │ Letzte Aktivität: Heute 14:30   │   │
│  └─────────────────────────────────┘   │
│                                         │
│  📋 VERGANGENE SESSIONS                │
│  ┌─────────────────────────────────┐   │
│  │ [Kompakte Liste/Tabelle]        │   │
│  │ - Heute 14:30: 5 Seiten, €0.50 │   │
│  │ - Gestern 10:15: 12 Seiten, ...│   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ [ "Drucksession starten" ]      │   │
│  └─────────────────────────────────┘   │
│        (Nur sichtbar wenn kein anderer │
│         eine Session hat)              │
└─────────────────────────────────────────┘
```

#### Layout (wenn Session aktiv):

```
┌─────────────────────────────────────────┐
│  Drucken & Scannen                      │
├─────────────────────────────────────────┤
│                                         │
│  [Status-Info bleibt oben sichtbar]     │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ ⏱️ AKTIVE SESSION               │   │
│  │ Restzeit: 23:45                 │   │
│  │ [ "Session beenden" ]           │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 📄 DRUCKEN                      │   │
│  │ ┌───────────────────────────┐   │   │
│  │ │ [Datei hochladen]         │   │   │
│  │ │ oder Drag & Drop          │   │   │
│  │ └───────────────────────────┘   │   │
│  │ Kopien: [ 1 ]                   │   │
│  │ [ "Drucken" ]                   │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 📷 SCANNEN                      │   │
│  │ Session aktiv - Bitte zum       │   │
│  │ Drucker gehen und scannen       │   │
│  │                                 │   │
│  │ [Gescannte Dokumente]           │   │
│  │ - scan_2025-01-15_14_32.pdf    │   │
│  │ - scan_2025-01-15_14_35.pdf    │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [Vergangene Sessions bleibt sichtbar] │
└─────────────────────────────────────────┘
```

### Sidebar-Integration

```typescript
// In routesConfig.tsx
{
  id: "printing",
  path: "/print",
  element: <Pages.PrintingPage />,
  title: "Drucken",
  icon: <PrintIcon />,
  requiredGroups: ["tenant", "ADMIN"],
  sidebar: true,
}
```

---

## User Interface - Referat Verwaltungsansicht

### Hauptseite: `/printing/management`

Das verantwortliche Referat (in dessen Zimmer der Drucker steht) erhält eine Admin-Übersicht:

```
┌─────────────────────────────────────────┐
│  Drucker-Verwaltung                     │
│  (für [Referatsname], z.B. Kreativreferat) │
├─────────────────────────────────────────┤
│                                         │
│  📊 DRUCKERSTATUS                       │
│  ┌─────────────────────────────────┐   │
│  │ Status: Aktiv / Deaktiviert     │   │
│  │ Letzte Aktivität: Heute 14:30   │   │
│  │ Toner: 85% | Papier: ✓          │   │
│  │ Fehler: Keine                    │   │
│  └─────────────────────────────────┘   │
│                                         │
│  💰 FINANZÜBERSICHT                     │
│  ┌─────────────────────────────────┐   │
│  │ Diesen Monat:                  │   │
│  │   Drucke: 234 Seiten            │   │
│  │   Einnahmen: €23.40             │   │
│  │                                 │   │
│  │ Letzte 7 Tage:                  │   │
│  │   Drucke: 45 Seiten             │   │
│  │   Einnahmen: €4.50              │   │
│  └─────────────────────────────────┘   │
│                                         │
│  📈 NUTZUNGSSTATISTIK                   │
│  ┌─────────────────────────────────┐   │
│  │ Top Nutzer (dieser Monat):      │   │
│  │   1. Max Mustermann: 45 Seiten  │   │
│  │   2. Anna Schmidt: 32 Seiten    │   │
│  │   3. ...                        │   │
│  └─────────────────────────────────┘   │
│                                         │
│  🔧 VERWALTUNG                          │
│  ┌─────────────────────────────────┐   │
│  │ [Toggle: Drucker aktivieren]    │   │
│  │ [Toggle: Neue Sessions erlauben]│   │
│  │ Preis pro Seite: [€0.10] [Speichern]│ │
│  │ Max Session-Dauer: [30 min] [Speichern]│ │
│  └─────────────────────────────────┘   │
│                                         │
│  📋 AKTUELLE SESSION                    │
│  ┌─────────────────────────────────┐   │
│  │ Aktive Session:                 │   │
│  │   Nutzer: Max Mustermann        │   │
│  │   Gestartet: 14:30              │   │
│  │   Restzeit: 25:30               │   │
│  │   [ Session beenden ]           │   │
│  └─────────────────────────────────┘   │
│                                         │
│  📜 DRUCKHISTORIE                       │
│  ┌─────────────────────────────────┐   │
│  │ [Filter: Heute / Diese Woche / Dieser Monat]│ │
│  │ [Tabelle mit allen Druckjobs]   │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Verwaltungsfunktionen

1. **Drucker Ein-/Ausschalten**
   - Global aktivieren/deaktivieren
   - Bei deaktiviert: keine neuen Druckjobs, keine neuen Sessions

2. **Session-Management**
   - Neue Sessions blockieren/erlauben
   - Aktive Session beenden
   - Maximale Session-Dauer setzen

3. **Preis-Konfiguration**
   - Preis pro Seite (z. B. €0.10)
   - Optional: Preis pro Farbe/Schwarz-Weiß
   - Änderungen protokollieren

4. **Statistiken & Übersichten**
   - Nutzung (Seiten, Jobs) über Zeiträume
   - Top-Nutzer
   - Einnahmen
   - Gerätestatus (Toner, Papier, Fehler via CUPS/SNMP)

5. **Historische Daten**
   - Druckhistorie mit Filtern
   - Export (z. B. CSV)
   - Kosten pro Nutzer

---

## API-Endpunkte

### Tenant-Endpunkte (`/api/tenants/printing/`)

```
GET  /api/tenants/printing/device-status/
     → Aktueller Druckerstatus (verfügbar/belegt, aktive Session-Info)

GET  /api/tenants/printing/my-costs/
     → Kostenübersicht (dieser Monat, Gesamt, etc.)

GET  /api/tenants/printing/my-sessions/
     → Vergangene Sessions des eingeloggten Users

POST /api/tenants/printing/sessions/start/
     → Neue Session starten (nur wenn möglich)

GET  /api/tenants/printing/sessions/{session_id}/
     → Session-Details abrufen

POST /api/tenants/printing/sessions/{session_id}/end/
     → Eigene Session beenden

POST /api/tenants/printing/sessions/{session_id}/print/
     → Druckjob erstellen (Datei-Upload als Multipart)

GET  /api/tenants/printing/sessions/{session_id}/jobs/
     → Alle Druckjobs einer Session

GET  /api/tenants/printing/sessions/{session_id}/scans/
     → Alle Scans einer Session

GET  /api/tenants/printing/scans/{scan_id}/download/
     → Gescanntes Dokument herunterladen
```

### Referat-Verwaltungsendpunkte (`/api/printing/`)

```
GET  /api/printing/device/{device_id}/overview/
     → Übersicht mit Status, Kosten, Statistiken

GET  /api/printing/device/{device_id}/statistics/
     → Detaillierte Statistiken (optional mit Zeitraum-Parametern)

PUT  /api/printing/device/{device_id}/settings/
     → Preis, Session-Dauer, etc. ändern

POST /api/printing/device/{device_id}/toggle-active/
     → Drucker global ein/ausschalten

POST /api/printing/device/{device_id}/toggle-sessions/
     → Neue Sessions erlauben/blockieren

POST /api/printing/device/{device_id}/terminate-session/
     → Aktive Session beenden

GET  /api/printing/device/{device_id}/history/
     → Druckhistorie mit Filtern

GET  /api/printing/device/{device_id}/export-csv/
     → Export als CSV
```

### Admin-Endpunkte (optional, für globale Verwaltung)

```
GET  /api/department/printing/devices/
     → Liste aller Devices (für ADMIN)

POST /api/department/printing/devices/
     → Neues Device erstellen (für ADMIN)

PUT  /api/department/printing/devices/{device_id}/
     → Device bearbeiten (für ADMIN)

DELETE /api/department/printing/devices/{device_id}/
     → Device löschen (für ADMIN)
```

---

## Permissions & Berechtigungen

### Tenant-Berechtigungen

- Alle authentifizierten Tenants können grundsätzlich drucken/scannen
- Einschränkungen:
  - Gerät muss aktiv sein (`device.is_active = True`)
  - Neue Sessions müssen erlaubt sein (`device.allow_new_sessions = True`)
  - Keine aktive Session von anderem User vorhanden

### Referat-Berechtigungen

- Referat-Mitglieder können das Device verwalten, wenn:
  - Sie Mitglied der LDAP-Gruppe des Referats sind (z.B. "Kreativreferat")
  - UND das Device dem Department des Referats zugeordnet ist
- Verwaltungsrechte:
  - Settings ändern
  - Toggles (aktivieren/deaktivieren)
  - Sessions beenden
  - Statistiken einsehen
  - Historie exportieren

### Permission-Check (Backend)

```python
def has_device_management_permission(user, device):
    """Prüft ob User das Device verwalten darf"""
    user_groups = [group.name for group in user.groups.all()]
    device_department_group = device.department.name  # z.B. "Kreativreferat"
    
    return device_department_group in user_groups or 'ADMIN' in user_groups
```

---

## Technische Details

### Geräte- und Infrastruktur

- **Raspberry Pi 4 Modell B** dient als Printserver
- Linux + CUPS installiert
- Drucker per USB am Pi
- SmartDorm sendet Druckjobs per HTTP API oder CUPS Python Library
- Der Pi kann Seitenzähler per SNMP lesen (optional für Analysen)
- Webinterface für CUPS bleibt nur für interne Admin-Konfiguration sichtbar

### Integration mit CUPS

- SmartDorm kommuniziert mit Raspberry Pi/CUPS über HTTP API
- Alternative: Direkte CUPS Python Library Integration
- Status-Abfrage: Printjob-Status regelmäßig abfragen
- Seitenzähler: SNMP-Abfrage für genaue Seitenzählung (optional)

### Scan-Integration

- Drucker sendet Scans an Pi (SMB/FTP/HTTP)
- Pi ordnet Scans der aktiven Session zu
- Scans werden in SmartDorm gespeichert
- Storage: MEDIA_ROOT für gescannte Dateien (nicht in DB als Binary)

### File-Handling

- Upload: PDF (MVP), später weitere Formate
- Storage: Temporärer Upload, dann an CUPS weiterleiten
- Scans: In MEDIA_ROOT speichern, Pfad in DB

### Background-Jobs (optional)

- Status-Updates: Regelmäßige Abfrage von CUPS-Job-Status
- Session-Timeout: Automatisches Beenden abgelaufener Sessions
- Empfehlung: Celery/RQ für asynchrone Tasks (aktuell nicht vorhanden)

---

## Implementierungsplan

### Phase 1: Datenmodell & Grundstruktur

1. Models erstellen (`Device`, `PrintSession`, `PrintJob`, `Scan`)
2. Migrations
3. Basis-Serializers
4. Basis-Views (Read-Only erstmal)

### Phase 2: Tenant-Funktionalität

1. Session-Management (starten, beenden)
2. Druckjob-Upload und -Erstellung
3. CUPS-Integration (Printjob senden, Status abfragen)
4. Frontend: `/print` Seite für Tenants

### Phase 3: Scan-Funktionalität

1. Scan-Receiving auf Raspberry Pi
2. Session-Zuordnung von Scans
3. Scan-Speicherung in SmartDorm
4. Frontend: Scan-Anzeige und Download

### Phase 4: Referat-Verwaltung

1. Device-Verwaltung (Settings, Toggles)
2. Statistiken und Übersichten
3. Historie-Export
4. Frontend: `/printing/management` Seite

### Phase 5: Feinschliff & Optimierung

1. Error-Handling verbessern
2. Performance-Optimierungen
3. Tests
4. Dokumentation

---

## Wichtige Einschränkungen für MVP

- Keine Offline-Kopierkosten
- Kein LDAP direkt am Drucker
- Keine Geräte-Power-Steuerung (keine Smart-Steckdose)
- Session-Zuordnung gilt als einzige Authentifikation am Gerät
- Nur PDF-Upload (keine anderen Formate)
- Kein automatischer E-Mail-Versand von Scans
- Kein Guthaben-System (nur Tracking)

---

## Feature-Roadmap (für spätere Iterationen)

- Direkte Authentifizierung am Drucker (PIN / Web-Kiosk)
- Automatische Tarifzonen / Guthabenmodelle
- Schnelle Dokumentvorschau im Web
- Live-Gerätestatus (Tonerstand, Papier, Fehler)
- Kopierkosten anhand von Page Counter Differenzen
- Scan-Verwaltung in Benutzer-Dokumentbibliothek
- Wartungsmodus (nur Referat kann drucken)
- Quotas (max Seiten pro Tag/Monat)
- Benachrichtigungen (Email bei Fehlern)
- Zugriffszeiten (Zeitfenster)
- Kostenerstattung durch Referat

---

## Integration mit bestehenden SmartDorm-Komponenten

### Ähnlichkeiten mit bestehenden Features

1. **Engagement Applications**: File-Upload, Status-Tracking
2. **Parcel Management**: Status-Tracking, Benachrichtigungen
3. **Departure Process**: Multi-Step-Workflow mit Status
4. **Department Signatures**: Referat-Verwaltung, Permissions

### Verwendete Patterns

- **Session-Authentication**: Wie bestehende Login-Sessions
- **Permission-System**: `GroupAndEmployeeTypePermission` wiederverwenden
- **Transaction-Management**: `@transaction.atomic` für kritische Operationen
- **Email-Benachrichtigungen**: `email_utils.send_email_message` (optional)
- **LDAP-Integration**: Für Referat-Permissions (ähnlich Department Signatures)

---

## Offene Fragen & Entscheidungen

1. **CUPS-Integration**: HTTP API oder Python Library?
2. **Scan-Protokoll**: SMB, FTP, oder HTTP für Scan-Upload vom Pi?
3. **Storage**: MEDIA_ROOT konfigurieren oder extern (S3)?
4. **Background-Jobs**: Celery/RQ einführen oder Threading (wie PDF-Regenerierung)?
5. **Seitenzählung**: CUPS-Job-Info oder SNMP Page Counter?
6. **Session-Timeout**: Wie lange? Konfigurierbar?
7. **Error-Handling**: Wie mit fehlgeschlagenen Druckjobs umgehen?

---

## Referenzen

- CUPS Documentation: https://www.cups.org/documentation.html
- Django REST Framework: https://www.django-rest-framework.org/
- Bestehende SmartDorm-Dokumentation in `/docs/`

---

**Dokument erstellt:** 2025-01-15  
**Status:** Planung abgeschlossen, Implementierung steht noch aus


