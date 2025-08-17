# Database Schema & Models

The SmartDorm database schema is a mix of legacy tables (with `managed = False` in Django) and new, Django-managed tables. Understanding these models is critical to working with the backend.

Most legacy tables are prefixed with `t_`.

## Core Models

### `Tenant` (`t_tenant`)
This is the central model of the application. It represents a resident of the dormitory.
*   **Key Fields**:
    *   `id`: Primary key (not auto-incrementing).
    *   `username`: The tenant's unique login name, linked to their LDAP account.
    *   `name`, `surname`, `email`: Personal details.
    *   `move_in`, `move_out`: The start and end dates of their contract.
    *   `current_room`, `current_floor`: Denormalized fields for their current location.
    *   `extension`: A counter for how many times their contract has been extended.

### `Departure` (`t_departure`)
A one-to-one relationship with `Tenant`. This model manages the entire move-out process for a tenant.
*   **Key Fields**:
    *   `tenant`: A `OneToOneField` link to the `Tenant`.
    *   `status`: The current stage of the departure process. Crucial states include:
        *   `CREATED`: The process has been initiated by the administration.
        *   `CONFIRMED`: The tenant has confirmed they are moving out. This triggers the signature process.
        *   `POSTPONED`: The tenant has requested a contract extension.
        *   `CLOSED`: The process is complete, all signatures are collected.

### `DepartmentSignature` (`t_department_signature`)
Represents a sign-off from a specific department for a departing tenant. This is used to track and settle debts or return borrowed items.
*   **Key Fields**:
    *   `departure`: A `ForeignKey` to the `Departure` record.
    *   `department_name`: The name of the department (e.g., "BAR", "WERK", "H1R1").
    *   `amount`: The amount of debt the tenant owes to this department.
    *   `signed_on`: A date field. It holds a sentinel value (`1900-01-01`) until the department signs off, at which point it's updated to the current date.

### `Claim` (`t_claim`)
Represents a formal request from a tenant, primarily for contract extensions.
*   **Key Fields**:
    *   `tenant`: A `ForeignKey` to the requesting `Tenant`.
    *   `type`: The type of claim, currently only `EXTENSION`.
    *   `status`: The state of the claim (`CREATED`, `PROCESSING`, `APPROVED`, `REJECTED`).

### `Engagement` (`t_engagement`)
Represents a tenant's official role in a department for a specific semester.
*   **Key Fields**:
    *   `tenant`: `ForeignKey` to the `Tenant`.
    *   `department`: `ForeignKey` to the `Department`.
    *   `semester`: The academic semester (e.g., "WS24/25").
    *   `points`: Points awarded for this engagement.
    *   `compensate`: A boolean indicating if the points have been compensated.

### `EngagementApplication` (`t_engagement_application`)
A record of a tenant's application to join a department for an upcoming semester.
*   **Key Fields**:
    *   `tenant`, `department`, `semester`: Links the application to the applicant, the desired department, and the target semester.
    *   `motivation`: The text of their application.
    *   `image`: An optional image for the application.

### `Department` (`t_department`)
Represents a student-run department (e.g., "Barreferat", "Finanzreferat").
*   **Key Fields**: `name`, `full_name`, `points` (standard points for a role in this dept).

### `GlobalAppSettings` (`t_global_app_settings`)
This is a **Django-managed** (`managed = True`) singleton model. It holds global state for the application, editable by administrators (Heimrat).
*   **Key Fields**:
    *   `current_semester`: The active academic semester. Drives many engagement-related features.
    *   `applications_open`: A boolean flag to enable or disable new engagement applications.
    *   `show_applications`: A boolean flag to control the visibility of submitted applications to all tenants.

## Supporting Models

*   **`Subtenant` (`t_subtenant`)**: A temporary resident staying in a tenant's room. They have limited access and a separate LDAP account creation flow.
*   **`Parcel` (`t_parcel`)**: Tracks parcels received for tenants and subtenants.
*   **`Room` (`t_room`)**: A record for each room in the dormitory.
*   **`Rental` (`t_rental`)**: A historical log of which tenant occupied which room and when. This provides a tenant's housing history.
*   **`DepositBank` (`t_deposit_bank`)**: Stores the tenant's bank details for the deposit refund upon moving out.