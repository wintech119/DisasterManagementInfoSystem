# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (2025-11-20)
- **Menu Item Rename - Relief Fulfillment Packages (Complete)**: Renamed "Prepare Fulfillment Packages" to "Relief Fulfillment Packages" for better clarity and consistency with DRIMS terminology. Change: Updated the `name` field from `'Prepare Fulfillment Packages'` to `'Relief Fulfillment Packages'` in the `package_preparation` feature entry in `app/core/feature_registry.py` (line 178). This change affects all users and roles (LOGISTICS_OFFICER, LOGISTICS_MANAGER) who use this functionality. The menu item now appears as "Relief Fulfillment Packages" in the navigation menu under the Packaging section.
- **Approved Packages Queue for Logistics Officers (Complete)**: Added a new "Approved Packages" queue/tab for Logistics Officers to track packages that have been approved by Logistics Managers and dispatched to Inventory Clerks. Changes: (1) **New Route** - Added `/packaging/approved-packages` route in `app/features/packaging.py` (line 1581) accessible to LOGISTICS_OFFICER and LOGISTICS_MANAGER roles. (2) **New Template** - Created `templates/packaging/approved_packages.html` with modern UI featuring filter tabs (Awaiting Handover, Completed, All) and summary cards. (3) **Feature Registry** - Added `approved_packages_queue` feature entry in `app/core/feature_registry.py` with navigation_group='packaging' and priority=13. (4) **Data Display** - Shows all packages with status_code='D' (Dispatched), including package ID, agency, items count, total quantity, approved date, handover status, and view details action. This allows LOs to track their packages through the approval and dispatch workflow without needing to access the Inventory Clerk's warehouse-specific view.
- **Menu Reorganization - Disaster Events (Complete)**: Moved the "Disaster Events" menu item under the "Management" section for better organization. Change: Updated `navigation_group` from `'relief_requests'` to `'master_data'` in the feature registry (line 309, `app/core/feature_registry.py`). The "Disaster Events" feature now appears in the Management menu alongside other master data items like Manage Warehouses, Item Categories, Manage Agencies, etc. This provides a more logical grouping as Disaster Events is a master data management function accessible to CUSTODIAN role.
- **Receive Inventory Feature Removal (Complete)**: Removed the "Receive Inventory" functionality from the entire system. Changes: (1) **Feature Registry** - Removed the `inventory_intake` feature entry from `app/core/feature_registry.py`, which was previously accessible to LOGISTICS_OFFICER, LOGISTICS_MANAGER, INVENTORY_CLERK, and SYSTEM_ADMINISTRATOR roles. (2) **Navigation** - The "Receive Inventory" menu item no longer appears in any user's navigation menus. (3) **Dashboard Widgets** - Removed `pending_intake_widget` dashboard widget reference. (4) **Access Control** - No users or roles can now access the `/intake/list` route or related intake functionality. Note: The underlying intake blueprint and templates remain in the codebase but are inaccessible through the UI due to feature registry removal. Result: "Receive Inventory" functionality is completely hidden from all users and roles in the system.

## User Preferences
- **Communication style**: Simple, everyday language.
- **UI/UX Requirements**:
  - All pages MUST have consistent look and feel with Relief Package preparation pages
  - Modern, polished design with summary cards, filter tabs, and clean layouts
  - Easy to use and user-friendly across all features
  - Consistent navigation patterns throughout the application

## System Architecture

### Technology Stack
- **Backend**: Python 3.11, Flask 3.0.3
- **Database ORM**: SQLAlchemy 2.0.32 with Flask-SQLAlchemy
- **Authentication**: Flask-Login 0.6.3 with Werkzeug
- **Frontend**: Server-side rendering with Jinja2, Bootstrap 5.3.3, Bootstrap Icons
- **Data Processing**: Pandas 2.2.2

### System Design
The application employs a modular blueprint architecture with a database-first approach, built upon a pre-existing ODPEM `aidmgmt-3.sql` schema. Key architectural decisions and features include:
-   **UI/UX Design**: Emphasizes a consistent modern UI, comprehensive design system, shared Jinja2 components, GOJ branding, accessibility (WCAG 2.1 AA), and standardized workflow patterns. It features role-specific dashboards and complete management modules for various entities with CRUD operations, validation, and optimistic locking.
-   **Notification System**: Includes real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations.
-   **Donation Processing**: Manages the full workflow for donations, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory.
-   **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table.
-   **Data Flow Patterns**: Supports an end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities.
-   **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy.

## External Dependencies

### Required Database
- **PostgreSQL 16+** (production) with `citext` extension.
- **SQLite3** (development fallback).

### Python Packages
- Flask
- Flask-SQLAlchemy
- Flask-Login
- SQLAlchemy
- psycopg2-binary
- Werkzeug
- pandas
- python-dotenv

### Frontend CDN Resources
- Bootstrap 5.3.3 CSS/JS
- Bootstrap Icons 1.11.3
- Flatpickr (latest)