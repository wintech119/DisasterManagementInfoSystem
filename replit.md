# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (2025-11-20)
- **Notification Deep-Linking Update (Complete)**: Updated notification deep-links after menu consolidation to ensure all notifications route users to the correct locations. Changes: (1) **Package Approved Notifications for LOs/LMs** - Now deep-link to the "Approved for Dispatch" tab (`/packaging/pending-fulfillment?filter=approved_for_dispatch`) instead of the preparation page, providing immediate access to approved packages. (2) **Inventory Clerk Notifications** - Continue to link to the awaiting dispatch page for warehouse-specific handover. (3) **Agency User Notifications** - Link to request tracking page. All notification deep-links verified to work correctly after removing standalone menu items.
- **Menu Consolidation - Approve Packages Removed (Complete)**: Removed the duplicate "Approve Packages" menu item from the main navigation. Change: Removed the `package_approval` feature entry from `app/core/feature_registry.py` (was on line 186-197) as this functionality is now available as the "Awaiting Approval" tab within the "Relief Fulfillment Packages" page for Logistics Managers. This eliminates duplicate navigation items and provides a more streamlined, integrated workflow where LMs can see the full package lifecycle (Awaiting, In Progress, Awaiting Approval, Approved for Dispatch) within a single page.
- **Approved for Dispatch Tab Integration (Complete)**: Integrated "Approved for Dispatch" as a tab within the "Relief Fulfillment Packages" page instead of a separate menu item. Changes: (1) **Route Update** - Modified `/packaging/pending-fulfillment` route to handle `approved_for_dispatch` filter, which displays approved packages (status='D') instead of requests. (2) **Template Update** - Added "Approved for Dispatch" tab to `templates/packaging/pending_fulfillment.html` with informational alert stating packages shown are approved by LM and dispatched to Inventory Clerks for informational purposes only. (3) **Feature Registry** - Removed `approved_packages_queue` feature entry so it no longer appears as a separate menu item. (4) **Data Display** - Shows package ID, agency, items count, total quantity, approved date, handover status, and view details action. (5) **Transaction Summary Back Link** - Made the back button role-aware: LMs go back to Pending Approval, LOs go back to Approved Packages tab. This provides an integrated view of the full package lifecycle within a single page without cluttering the main navigation menu.
- **Menu Item Rename - Relief Fulfillment Packages (Complete)**: Renamed "Prepare Fulfillment Packages" to "Relief Fulfillment Packages" for better clarity and consistency with DRIMS terminology. Change: Updated the `name` field from `'Prepare Fulfillment Packages'` to `'Relief Fulfillment Packages'` in the `package_preparation` feature entry in `app/core/feature_registry.py` (line 178). This change affects all users and roles (LOGISTICS_OFFICER, LOGISTICS_MANAGER) who use this functionality. The menu item now appears as "Relief Fulfillment Packages" in the navigation menu under the Packaging section.
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