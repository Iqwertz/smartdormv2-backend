# Other Features

This document covers other important features of the SmartDorm backend that don't fall into the main lifecycle flows.

## Parcel Management

The system provides a simple way for the administration (`Verwaltung`) to manage incoming mail and parcels for residents.

*   **Recipient Identification**: When creating a parcel, the administrator can identify the recipient in one of two ways:
    1.  **By Room Number**: The system will look up the current `Tenant` assigned to that `current_room`. This is the preferred method as it's unique.
    2.  **By Name and Surname**: The system will search for a current `Tenant` or `Subtenant` matching the name. If multiple residents share the same name, the API will return an error and prompt the admin to use the room number instead.
*   **Notification**: Upon successful creation of a `Parcel` record, the system automatically sends an email to the recipient's registered address, informing them that they have mail to collect.
*   **Pickup**: The list of uncollected parcels is visible to the administration. When a resident collects their parcel, the admin marks it as picked up via the API, which records the `picked_up` timestamp.

## Subtenant Management

The system supports the management of subtenants, who are temporary residents living in a main tenant's room.

*   **Creation Flow**: The creation process for a subtenant is similar to that of a main tenant but with some key differences:
    *   It is initiated by the administration.
    *   A subtenant record (`Subtenant`) is linked to both the main `Tenant` they are subletting from and the `Room` they are occupying.
*   **LDAP Account**: A temporary LDAP account is created for the subtenant. However, they are added to a different set of LDAP groups (`DEFAULT_SUBTENANT_LDAP_GROUPS` in `config.py`), which typically grant them limited access (e.g., Wi-Fi access via the `wlan` group) compared to a full tenant.
*   **Deletion**: When a subtenant moves out, their database record and their temporary LDAP account are deleted.

## Shared Data Endpoints

To support the frontend and reduce redundant data transfer, a set of "common" endpoints exists under `/api/common/`. These endpoints provide simplified lists of objects that are frequently used to populate dropdown menus (`<select>`) or search fields.

*   `GET /api/common/tenant-list/`: Returns a list of all current tenants with just their ID and a formatted label (e.g., "John Doe (j.doe) - Room: 123").
*   `GET /api/common/room-list/`: Returns a simple list of all rooms with their ID and name.
*   `GET /api/common/departments-for-select/`: Returns a list of all departments with their ID and name.