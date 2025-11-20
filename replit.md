# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (2025-11-20)
- **Batch Selection Drawer UI Refinement (Complete)**: Improved the Select Batches side drawer on Prepare Relief Package page with more compact, scannable layout. Changes: (1) **Reduced Vertical Spacing** - Tightened padding throughout: warehouse headers (1.5rem → 0.875rem/1rem), batch items (1.5rem → 0.875rem), warehouse body (1.5rem → 0.875rem), and section margins (1.5rem → 1rem). (2) **Optimized Column Spacing** - Reduced gaps in batch details grid (1rem → 0.5rem/0.75rem) and allocation inputs (1rem → 0.5rem) for better information density. (3) **Improved Typography Hierarchy** - Warehouse names sized down (1.125rem → 1rem) with smaller icons (0.875rem), batch numbers reduced (1rem → 0.875rem), and consistent label/value spacing (0.25rem → 0.125rem) for cleaner alignment. (4) **Compact Input Controls** - Allocation inputs and "Use Max" buttons reduced (1rem padding → 0.625rem/0.75rem, base font → small font) while maintaining usability. Result: Multiple warehouses and batches now fit comfortably on screen, improving workflow efficiency. All existing colors, icons, DRIMS branding, collapsible behavior, and FEFO/FIFO logic preserved - CSS/spacing-only changes.
- **Inventory Clerk Access Restrictions (Complete)**: Updated role-based access controls for Inventory Clerks to restrict their access and visibility: (1) **Reports Access Removed** - Removed INVENTORY_CLERK role from all reports features (`reports_main`, `reports_inventory`, `reports_donations`) in Feature Registry. Inventory Clerks no longer see "Reports" in navigation menus or dashboards. (2) **Warehouse-Filtered Inventory** - Modified inventory listing (`/inventory`) to automatically filter inventory based on user's assigned warehouses for INVENTORY_CLERK role. Clerks can only see inventory from warehouses they are assigned to. Warehouse dropdown also filtered to show only assigned warehouses. Other roles (LO, LM, SYSADMIN) continue to see all warehouses. This ensures data isolation and prevents clerks from viewing or accessing inventory from other warehouses.
- **Location Management Removal (Complete)**: Removed the "Manage Locations" functionality from the entire application. Removed: (1) `app/features/locations.py` blueprint with all CRUD routes, (2) `templates/locations/` directory with all location templates, (3) `location_management` feature from Feature Registry, (4) All navigation entries and role-based access controls for location management. The Location table remains in the database schema for future use but is no longer accessible through the application UI.
- **Dispatch Slip UI Modernization (Complete)**: Updated the Dispatch Slip page (`/packaging/dispatch/<package_id>/details`) with a clean, modern design while preserving all existing functionality. Changes include: (1) **Modern Visual Design** - Clean card-based layout with gradient headers, subtle shadows, and improved color scheme matching DRIMS branding. (2) **Organized Sections** - Agency Information, Dispatch Details, Items by Warehouse, and Signature Section all clearly separated with professional styling. (3) **Enhanced UX** - Modern action buttons with hover effects, status badges with icons, color-coded information, and improved table layouts with hover effects. (4) **Print-Optimized** - Professional print layout suitable for official documentation with clean signature block and ODPEM branding footer. (5) **Functionality Preserved** - All buttons ("Print Dispatch Slip", "Mark as Handed Over") work exactly as before with no changes to backend logic, permissions, or routing.

## Recent Changes (2025-11-19)
- **Warehouse-Specific Dispatch Receiving (Complete)**: Implemented comprehensive dispatch receiving workflow for Inventory Clerks with feedback queues for Logistics Officers and Managers. Key features: (1) **Inventory Clerk - Awaiting Dispatch** - New page showing packages approved by LM and dispatched, filtered by clerk's assigned warehouse(s). Displays only items allocated from warehouses the clerk has access to, with summary cards and filter tabs (Awaiting Handover, Completed, All). (2) **Dispatch Details with Print Slip** - Full dispatch details page with print-friendly layout including agency signature section (Received By, Signature, Date). Items grouped by warehouse with batch/lot info and expiry dates. (3) **Mark as Handed Over** - Inventory Clerks can mark packages as handed over to agencies, updating `received_by_id` and `received_dtime` with full audit trail. Action triggers notifications to LO/LM. (4) **LO/LM - Dispatch Received Queue** - New tab showing packages handed over by Inventory Clerks with warehouse information, handover timestamps, and read-only dispatch details with complete audit timeline. (5) **Notifications** - In-app notifications sent to all LO/LM users when Inventory Clerk marks handover, deep-linking to dispatch details. (6) **Feature Registry Integration** - Added `dispatch_awaiting` and `dispatch_received` features with role-based navigation for INVENTORY_CLERK and LOGISTICS_OFFICER/LOGISTICS_MANAGER respectively. All pages maintain consistent DRIMS UI patterns with summary cards, filter tabs, and modern layouts. No database schema changes - uses existing `received_by_id` and `received_dtime` fields in ReliefPkg table.
- **Unavailable Items Approval Support (Complete)**: Updated LM approval workflow to properly handle items marked as Unavailable (U), Denied (D), or Awaiting Availability (W). Key changes: (1) **Approval Logic Update** - LM can now approve packages where all items have zero allocation IF those items have valid unavailability statuses (U, D, W). Previously, approval was blocked when no items had allocated quantities. New validation allows approval when `all_items_unavailable` is true. (2) **Transaction Summary Enhancement** - Added new "Status" column to transaction summary report showing item fulfillment status with color coding (red for U/D/W, green for Filled, yellow for Partly Filled, cyan for Allowed Limit). Items with zero allocation now clearly show "No allocation made" in batch details section. Status reason displayed below status when provided. (3) **Model Relationship** - Added `item_status` relationship to ReliefRqstItem model (ForeignKey to reliefrqstitem_status table) to enable eager loading of status descriptions. No database schema changes required - only ORM relationship definition updated. (4) **Validation Fix for LO Submission** - Updated `_process_allocations` function to check item status before enforcing complete allocation requirement. Items with U/D/W status can now have zero allocation and be submitted for approval. This ensures agencies receive proper documentation even when items cannot be allocated, maintaining transparency in disaster relief operations.
- **Ready to Dispatch Tab Removal (Complete)**: Removed "Ready for Dispatch" tab and all associated data from Pending Fulfillment page. Removed summary card from metrics, removed filter tab, removed backend logic, and removed all count calculations. Page now shows only: "Awaiting to be Filled", "Being Prepared", "Awaiting Approval" (LM only), and "All" tabs.

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
-   **Donation Processing**: Manages the full workflow for donations, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory. Automatic verification upon acceptance is a key feature.
-   **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency (uppercase varchars), auditability, precision (`DECIMAL(15,4)`), and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table.
-   **Data Flow Patterns**: Supports an end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities. Utilizes dedicated services like `ItemStatusService` and `InventoryReservationService`.
-   **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Specific CRUD operations are restricted by role.

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