# SmartDorm Backend Documentation

Welcome to the developer documentation for the SmartDorm backend. This system is a Django-based application designed to manage the administrative and community aspects of the Schollheim student dormitory.

This documentation provides a high-level overview of the application's architecture, key concepts, and data flows. It is intended for developers who will be maintaining or extending the system.

## Used Technologies

*   **Backend Framework:** Django & Django REST Framework (DRF)
*   **Database:** PostgreSQL
*   **Authentication:** LDAP (via `django-auth-ldap`)
*   **Session Management:** Redis (via `django-redis`)
*   **Asynchronous Tasks:** (Not currently implemented, but a potential future addition)
*   **Email:** Django's email backend with an SMTP server.

## Navigating the Documentation

To get a full understanding of the system, please read through the following sections:

1.  [**Database Schema & Models**](./database_schema.md): An essential guide to understanding the data structure, including the core tables and their relationships.
2.  [**Tenant Lifecycle**](./tenant_lifecycle.md): Explains the complete journey of a tenant, from moving in, requesting an extension, to the final move-out process.
3.  [**Engagement Management**](./engagement_management.md): Details how tenants apply for and are assigned to student-run departments ("Referate"), and how the critical semester changeover process works.
4.  [**Authentication & Permissions**](./authentication_permissions.md): Describes how users are authenticated against LDAP and how access to different API endpoints is controlled.
5.  [**API Endpoint Overview**](./api_endpoints.md): A high-level summary of the available API endpoints and their purpose.
6.  [**Other Features**](./other_features.md): Documentation for other key functionalities like Parcel and Subtenant management.