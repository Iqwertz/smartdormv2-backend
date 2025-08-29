# API Endpoint Overview

This document provides a high-level overview of the API structure. All endpoints are prefixed with `/api/`.

### Authentication (`/api/auth/`)
*Handles user login, logout, and session status.*
*   `POST /login/`: Authenticates a user against LDAP and creates a session.
*   `POST /logout/`: Destroys the current session.
*   `GET /me/`: Returns information about the currently logged-in user.

### Tenant-Facing Endpoints (`/api/tenants/`)
*Endpoints used by logged-in tenants.*
*   `GET /profile-data/`: Retrieves the `Tenant` profile of the logged-in user.
*   `GET /my-engagements/`: Lists all past and present engagements for the tenant.
*   `GET /my-departure/`: Fetches the tenant's open departure request, if one exists.
*   `POST /my-departure/decide/`: Allows the tenant to confirm their departure or request an extension.
*   `GET/POST/DELETE /engagement-application/...`: Endpoints for creating, viewing, and deleting engagement applications.
*   `GET /global-settings/`: Retrieves the current global application settings (e.g., current semester).

### Department & Admin Endpoints (`/api/department/`)
*Endpoints used by administration (`Verwaltung`), department members, and other privileged roles.*
*   **Tenant Management**:
    *   `GET /tenant-data/`: Lists tenants (filterable by current, past, future).
    *   `POST /create-new-tenant/`: Creates a new tenant and their LDAP account.
    *   `PUT /tenant-data/{id}/update/`: Updates tenant details.
    *   `DELETE /tenant-data/{id}/delete/`: Deletes a tenant and their LDAP account.
*   **Subtenant Management**:
    *   `GET/POST/PUT/DELETE /subtenants/...`: Full CRUD operations for subtenants.
*   **Parcel Management**:
    *   `POST /parcels/create/`: Creates a new parcel record and notifies the recipient.
    *   `GET /parcels/list/`: Lists parcels (pending, picked up, or all).
    *   `POST /parcels/{id}/pickup/`: Marks a parcel as picked up.
*   **Departure & Claim Management**:
    *   `GET/POST /departures/...`: Manages the entire departure lifecycle (creation, listing candidates, closing).
    *   `GET/POST /claims/...`: Manages extension requests (listing, deciding).
*   **Signatures**:
    *   `GET /signatures/{slug}/list/`: Lists pending or completed signatures for a specific department.
    *   `PUT /signatures/{id}/update/`: Allows a department to sign off on a departing tenant.

### Engagement Admin Endpoints (`/api/engagements/`)
*Endpoints restricted to the Heimrat for managing engagements.*
*   **Application Management**:
    *   `GET /heimrat/applications/list/`: Privileged view of all engagement applications.
    *   `GET /heimrat/applications/`: Generates a consolidated PDF of all applications.
    *   `POST/DELETE /heimrat/applications/...`: Create or delete applications on behalf of tenants.
*   **Engagement Management**:
    *   `GET/POST/DELETE /heimrat/engagements/...`: Full CRUD for official `Engagement` records.
*   **Settings Management**:
    *   `POST /heimrat/set-semester/`: Sets the `current_semester`.
    *   `POST /heimrat/set-applications-open/`: Opens or closes the application window.
    *   `POST /heimrat/update-semester-and-ldap/`: **CRITICAL** endpoint to perform the semester changeover and LDAP group synchronization.

### Common Endpoints (`/api/common/`)
*Provides shared data for frontend UI elements.*
*   `GET /tenant-list/`: A simplified list of current tenants for dropdowns.
*   `GET /room-list/`: A list of all rooms.
*   `GET /departments-for-select/`: A list of all departments.