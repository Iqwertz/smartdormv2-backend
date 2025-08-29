# Engagement Management

"Engagements" refer to a tenant's participation in a student-run department ("Referat"). This system manages the entire lifecycle, from applications to the official semester changeover. The process is primarily managed by the "Heimrat" group.

## Global Configuration

The entire process is governed by settings in the `GlobalAppSettings` model:

*   `current_semester`: Defines the active semester. This is the source of truth for many queries.
*   `applications_open`: A boolean controlled by Heimrat. When `true`, tenants can submit applications for the *next* semester.
*   `show_applications`: A boolean controlled by Heimrat. When `true`, all submitted applications are visible to every tenant to promote transparency.

## 1. The Application Process

*   **Trigger**: Heimrat sets `applications_open` to `true`.
*   **Tenant Action**: Tenants fill out an application form in the frontend.
*   **API Endpoint**: `POST /api/tenants/engagement-application/`
*   **Process Flow**:
    1.  The view checks if applications are open.
    2.  It identifies the applicant via their session and determines the target semester by calling the `get_next_semester()` helper function.
    3.  It validates that the tenant has not already applied for the same department in the target semester.
    4.  A new `EngagementApplication` record is created, storing the motivation text and an optional image.

## 2. Reviewing Applications

*   **Public View**: If `show_applications` is `true`, all tenants can see the applications (without contact details) at `GET /api/tenants/engagement-applications/`.
*   **Heimrat View**: Heimrat has a privileged view with more details at `GET /api/engagements/heimrat/applications/list/`.
*   **PDF Export**: Heimrat can generate a single PDF document containing all applications, grouped by department, for offline review and meetings.
    *   **API Endpoint**: `GET /api/engagements/heimrat/applications/`

## 3. Assigning Engagements

The selection and voting process happens outside the application. Once decisions are made, Heimrat formalizes them in the system.

*   **Trigger**: Heimrat uses an admin interface to assign tenants to departments for the upcoming semester.
*   **API Endpoint**: `POST /api/engagements/heimrat/engagements/create/`
*   **Process Flow**: This creates an `Engagement` record, which is the official link between a tenant, a department, and a semester.

## 4. The Semester Changeover (Critical Operation)

This is a powerful and critical administrative action that officially transitions the system from one semester to the next.

*   **Trigger**: A Heimrat member initiates the semester update via the admin panel.
*   **API Endpoint**: `POST /api/engagements/heimrat/update-semester-and-ldap/`
*   **Process Flow**: This endpoint performs a series of actions within a single database transaction. If any step fails, the entire operation is rolled back.
    1.  **Input**: The endpoint receives the `new_semester` string (e.g., "SS25").
    2.  **LDAP Group Removal**: The system fetches all `Engagement` records for the `old_semester`. It iterates through them and removes each tenant from their respective department's LDAP group (e.g., user `j.doe` is removed from the `cn=bar,...` LDAP group).
    3.  **LDAP Group Addition**: The system fetches all `Engagement` records for the `new_semester`. It iterates through them and adds each tenant to their new department's LDAP group.
    4.  **Database Update**: If all LDAP operations complete successfully, the system updates `GlobalAppSettings.current_semester` to the `new_semester`.
    5.  **Commit or Rollback**: If the process was successful, the database transaction is committed. If any LDAP error occurred, an exception is raised, and the transaction is rolled back, leaving the `current_semester` unchanged.