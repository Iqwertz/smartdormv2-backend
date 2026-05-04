# Attendance Tracking System

This document outlines the architecture, requirements, and technical implementation of the generic QR-code based Attendance Tracking system (e.g., for General Assemblies / "Vollversammlungen", Bar Duties, and other mandatory or voluntary dorm events).

## Purpose & Requirements

The goal of this feature is to replace manual roll calls and paper sign-in sheets with a reliable, automated, and cheat-proof digital system, while retaining administrator oversight. 

**Key Requirements:**
1. **Generic Event Support:** The system must support diverse events with custom names, configurable parts (e.g., an event split into multiple sessions), and definable attendance requirements.
2. **Link-based QR Flow:** The projector QR opens SmartDorm in the browser with a single attendance code in the URL. The code is composed as `sessionId_token`.
3. **Optional Browser Check-in:** When enabled, the browser can register attendance directly after login. When disabled, only the in-app scanner can submit attendance.
4. **In-App Native Scanner:** To prevent cheating, attendees may still scan the QR code from within the authenticated SmartDorm frontend application.
5. **Rotating QR Codes:** The QR code projected on the wall must rotate continuously (e.g., new token every 60 seconds) to ensure physical presence at the event.
6. **Dynamic Authorization:** Different events can be managed by different administrative bodies. The system must restrict event management to specific LDAP groups (e.g., Heimrat, Organizers).
7. **Manual Management & Overrides:** Organizers must be able to manually open and close physical sessions. They also need a matrix/report view to manually tick or untick attendance for specific tenants if the scanner fails, a phone battery dies, or an exemption is granted.

## Database Schema

The implementation introduces three new Django models to `smartdorm/models.py`.

### 1. `Event`
Defines the generic event type and its rules.
*   **`name`**: The display name of the event (e.g., "Vollversammlung").
*   **`description`**: Optional details and instructions.
*   **`admin_groups`**: A JSON field containing an array of LDAP group names (e.g., `["heimrat", "vollversammlung_admin"]`) that have permission to manage this event and its sessions.
*   **`total_parts`**: The total number of sessions that make up this event.
*   **`required_parts`**: The threshold of parts a tenant must attend to be considered "fully attended."

### 2. `AttendanceSession`
Represents a specific, physical occurrence (or part) of an event.
*   **`event`**: ForeignKey linking back to `Event`.
*   **`title`**: Specific session title (e.g., "VV Sommersemester 2026 - Teil 1").
*   **`date`**: When the session takes place.
*   **`is_active`**: A boolean flag indicating if the session is currently accepting scans. Controlled manually by organizers.
*   **`part_number`**: An integer indicating which part of the parent event this session fulfills.
*   **`current_token` & `token_expires_at`**: Fields used strictly to manage the rotating QR code payload and its validity window.

### 3. `AttendanceRecord`
The transactional mapping representing a successful check-in.
*   **`session`**: ForeignKey linking to the `AttendanceSession`.
*   **`tenant`**: ForeignKey linking to the `Tenant`.
*   **`timestamp`**: Exact time the record was created.
*   **`manual_override`**: A boolean tracking whether this record was created via a native user scan (`False`) or if it was manually toggled by an admin (`True`).

## Backend Architecture

The business logic is implemented in `smartdorm/views/attendance_views.py`.

### Security & Authorization
The endpoints utilize a customized `GroupAndEmployeeTypePermission` architecture. When an admin attempts to access or modify an event, the system checks if the user's LDAP groups intersect with the `admin_groups` JSON array configured on the target `Event`.

### QR Token Rotation
When a session is marked `is_active`, the frontend projector periodically polls the `/api/attendance/sessions/<id>/qr_token/` endpoint. 
If the current time exceeds `token_expires_at`, the backend generates a fresh UUID `current_token`, updates the expiry to `now() + 60 seconds`, saves the session, and returns the new composite attendance code as `sessionId_token`.

### Check-in Endpoint (`/api/attendance/scan/`)
*   **Input**: A single `code` value formatted as `sessionId_token`.
*   **Validation**:
    1. Splits the session id from the token.
    2. Loads the matching `AttendanceSession` by id.
    3. Verifies the session is active and the token matches the current or recent previous token.
    4. Finds the `Tenant` record matching the `request.user`.
*   **Success**: Creates an `AttendanceRecord` for the tenant.

### Manual Override Endpoint (`/api/attendance/manual_override/`)
Allows admins to bypass the token system. Taking a `session_id` and `tenant_id`, this endpoint safely toggles the `AttendanceRecord` (creating it with `manual_override=True` or deleting it entirely).

## Frontend Architecture

The user interfaces are implemented in the React application (`smartdormv2-frontend/src`).

### Admin Experience
*   **`EventManagementPage.tsx`**: A CRUD interface for creating generic events, configuring required parts, and assigning administrative LDAP groups.
*   **`ActiveSessionDisplayPage.tsx`**: The "Projector View". This page hides standard navigation, maximizes the QR code (rendered via `qrcode.react`), and polls the backend every 10 seconds to fetch and display the rotating attendance link seamlessly.
*   **`AttendanceReportPage.tsx`**: A comprehensive data grid or matrix displaying all tenants globally against the current session. Admins can view scan timestamps and use toggle switches to invoke the `manual_override` API endpoint.

### Tenant Experience
*   **`AttendanceScannerPage.tsx`**: The mobile-first scanner interface utilizing `html5-qrcode`. It directly hooks into the device camera, parses the attendance link, extracts the composite code, and posts to the backend check-in endpoint.
*   **Browser check-in page**: When a QR link is opened in the browser, SmartDorm stores the code until login is available and then submits attendance automatically, if link check-in is enabled.
*   **`TenantPage.tsx` (`AttendanceHistoryCard.tsx`)**: Residents can review their own attendance history directly on their profile dashboard, seeing which events they satisfied and which ones they missed.

## Future Enhancements
*   **UI/UX Polish:** The UI structural layout is functional but requires aesthetic improvements (better responsive handling on the report grids, prettier scanner bounds, and refined animations).
*   **Offline Fallbacks:** Investigate caching mechanisms if the projector momentarily loses network access during a rotation cycle.
