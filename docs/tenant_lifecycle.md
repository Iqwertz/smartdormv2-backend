# Tenant Lifecycle Management

This document outlines the complete data flow for a tenant's journey within SmartDorm, from their arrival to their departure or contract extension.

## 1. Tenant Onboarding (Move-In)

The process of adding a new tenant is handled by the administration (`Verwaltung`).

*   **Trigger**: An administrator uses the frontend to submit a new tenant's details.
*   **API Endpoint**: `POST /api/department/create-new-tenant/`
*   **Process Flow**:
    1.  The `create_new_tenant_view` receives the request, which is validated by `NewTenantSerializer`.
    2.  A unique `username` is generated based on the tenant's name (e.g., `j.doe`).
    3.  The `ldap_utils.create_ldap_user` function is called. This creates a new user account in the LDAP directory and adds them to the default tenant groups defined in `config.py` (`DEFAULT_TENANT_LDAP_GROUPS`).
    4.  A new `Tenant` record is created in the database with the generated username and other details. Contract dates (`move_in`, `move_out`) and probation end are calculated.
    5.  Finally, `email_utils.send_email_message` sends a welcome email to the new tenant containing their login credentials.

## 2. The Departure Process

This is a multi-step process involving the administration, the tenant, and various student departments.

#### Step A: Initiation

1.  **Candidate Identification**: The system can identify tenants whose contracts are ending soon via the `GET /api/department/departures/candidates/` endpoint.
2.  **Creation**: An administrator creates a `Departure` record for a tenant via `POST /api/department/departures/create/`.
3.  The `Departure` status is set to `CREATED`.
4.  The tenant receives an email notification, prompting them to log in and make a decision about their departure.

#### Step B: Tenant's Decision

The tenant logs in and is presented with a choice.

*   **API Endpoint**: `POST /api/tenants/my-departure/decide/`
*   **Possible Decisions**:
    1.  **Confirm Departure (`decision: 'CONFIRM'`)**:
        *   The tenant provides their bank details (IBAN) for the deposit return, which are saved in the `DepositBank` table.
        *   The `Departure` status is updated to `CONFIRMED`.
        *   **Crucially, this triggers the signature process.** The `create_and_notify_departure_signatures` function is called, creating `DepartmentSignature` records for all required departments (e.g., Bar, Werk, Finanz, Tutoren, plus the tenant's floor).
        *   Each department receives an email notification about the pending sign-off.
    2.  **Request Extension (`decision: 'POSTPONE'`)**:
        *   The `Departure` status is updated to `POSTPONED`.
        *   A new `Claim` record is created with `type='EXTENSION'` and `status='CREATED'`.
        *   The administration is notified via email about the extension request.

#### Step C: Finalizing the Departure (after 'CONFIRM')

1.  **Department Sign-off**: Department members log in and view their pending signatures at `GET /api/department/signatures/{dept_slug}/list/`.
2.  They can update a signature to add a debt amount (`amount`) and finalize it.
3.  **API Endpoint**: `PUT /api/department/signatures/{signature_id}/update/`
4.  Updating the signature changes its `signed_on` date from the sentinel value (`1900-01-01`) to the current date, marking it as complete.
5.  **Closing the Departure**: Once all `DepartmentSignature` records are complete, an administrator can close the departure.
6.  **API Endpoint**: `POST /api/department/departures/{departure_id}/close/`
7.  The `Departure` status is set to `CLOSED`, and the process is complete.

## 3. Contract Extension (Handling Claims)

This flow begins after a tenant requests an extension (Step 2B).

1.  **Review**: The administration reviews the open `Claim` via `GET /api/department/claims/list/`.
2.  **Decision**: The administrator processes the decision.
3.  **API Endpoint**: `POST /api/department/claims/{claim_id}/decide/`
4.  **Outcomes**:
    *   **Approved (`decision: 'APPROVED'`)**:
        *   The `Claim` status is set to `APPROVED`.
        *   The `Tenant.move_out` date is updated to a new future date.
        *   The tenant's `extension` counter is incremented.
        *   The corresponding `Departure` record is deleted.
        *   The tenant is notified of the approval.
    *   **Rejected (`decision: 'REJECTED'`)**:
        *   The `Claim` status is set to `REJECTED`.
        *   The `Departure` record's status is changed from `POSTPONED` back to `CONFIRMED`.
        *   **This triggers the signature process** as described in Step 2C.
        *   The tenant is notified of the rejection and that the move-out process will now proceed.