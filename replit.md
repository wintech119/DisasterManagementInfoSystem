# DMIS - Disaster Management Information System

## Overview
DMIS (Disaster Management Information System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## User Preferences
- **Communication style**: Simple, everyday language.
- **UI/UX Requirements**:
  - All pages MUST have consistent look and feel with Relief Package preparation pages
  - Modern, polished design with summary cards, filter tabs, and clean layouts
  - Easy to use and user-friendly across all features
  - Consistent navigation patterns throughout the application

## Recent Updates (November 21, 2025)
- **Relief Package Draft Workflow Fix**: Fixed "Save as Draft" to correctly distinguish draft packages from submitted packages using a sentinel pattern. Draft packages now remain in "Being Prepared" tab without triggering approval workflow or notifications. Implementation uses `verify_by_id` field: NULL for drafts, '__PENDING_LM__' sentinel for submitted packages awaiting approval, and LM username for approved packages. Updated `has_pending_approval()` function to check for sentinel value, ensuring correct tab filtering and workflow state management.
- **Inventory Table Auto-Update on Dispatch**: Fixed inventory quantity synchronization during dispatch approval. The `commit_inventory()` function now automatically recalculates and updates `inventory.usable_qty` and `inventory.reserved_qty` after batch-level deductions. When LM approves dispatch, the system tracks affected inventory records, sums quantities from all related batches, and updates inventory totals in the same atomic transaction. This ensures inventory table always matches the sum of batch-level quantities, maintaining data consistency across the two-tier inventory system.
- **ItemBatch Schema Update - batch_no Nullable**: Changed `batch_no` column from NOT NULL to NULL constraint. Updated SQLAlchemy model (`app/db/models.py`) and executed `ALTER TABLE itembatch ALTER COLUMN batch_no DROP NOT NULL` to allow nullable batch numbers. This provides flexibility for items that don't require batch tracking.
- **UOM Auto-Populate for Donation Intake**: Implemented read-only UOM (Unit of Measure) enforcement in donation acceptance workflow. When LO/LM selects an item, the UOM field auto-populates from Item Master's `default_uom_code` and becomes disabled (greyed out) to prevent manual override. Backend updated to pass `default_uom_code` in items_json; frontend uses hidden input field to ensure UOM value is submitted with form. This ensures data consistency: all items use their master-defined UOM.
- **System Rebranding**: Complete rename from "DRIMS" to "DMIS" (Disaster Management Information System) across all user-facing text, templates, and documentation. All technical identifiers (routes, function names, database schemas) remain unchanged.
- **ItemBatch Schema Update - batch_date Nullable**: Changed `batch_date` column from NOT NULL to NULL constraint. Updated SQLAlchemy model (`app/db/models.py`) and database schema to allow nullable batch dates. All existing code already handles null values properly (BatchAllocationService, BatchCreationService, and frontend JavaScript). When null, batch_date defaults to today's date during creation and displays as 'N/A' in UI.
- **Operations Dashboard for Executives**: Created new executive-level Operations Dashboard (`/executive/operations`) with read-only KPIs and Chart.js visualizations for system-wide donations, relief requests, and fulfillment metrics. Accessible only to ODPEM_DG, ODPEM_DDG, and ODPEM_DIR_PEOD roles.
- **Executive Dashboard Routing**: Updated main dashboard routing to send executive roles (DG, Deputy DG, Director PEOD) to Operations Dashboard by default. Director Dashboard (eligibility workflow) remains accessible via navigation menu at `/director/dashboard`.
- **Relief Request Tab Counters**: All tab counters now show exact counts matching the number of requests in each tab's list using identical filtering logic. Added "All Requests" tab showing total count. Reorganized tabs: All Requests, Pending Review, Approved, Drafts, Completed.
- **Relief Request Sorting**: All relief request lists now sort by newest first (`.order_by(request_date.desc())` or `.order_by(create_dtime.desc())`), including main lists, workflow tabs, and eligibility queue.
- **Dynamic Status Dropdown**: Fixed batch allocation drawer to properly update status dropdowns by calling main page's `updateAllocation()` function.

## System Architecture
The application employs a modular blueprint architecture with a database-first approach, built upon a pre-existing ODPEM `aidmgmt-3.sql` schema.

### Technology Stack
- **Backend**: Python 3.11, Flask 3.0.3
- **Database ORM**: SQLAlchemy 2.0.32 with Flask-SQLAlchemy
- **Authentication**: Flask-Login 0.6.3 with Werkzeug
- **Frontend**: Server-side rendering with Jinja2, Bootstrap 5.3.3, Bootstrap Icons
- **Data Processing**: Pandas 2.2.2

### System Design
- **UI/UX Design**: Emphasizes a consistent modern UI, comprehensive design system, shared Jinja2 components, GOJ branding, accessibility (WCAG 2.1 AA), and standardized workflow patterns. Features role-specific dashboards and complete management modules for various entities with CRUD operations, validation, and optimistic locking.
- **Notification System**: Includes real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations.
- **Donation Processing**: Manages the full workflow for donations, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table.
- **Data Flow Patterns**: Supports an end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities.
- **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Features secure user management with role assignment restrictions to prevent privilege escalation; includes both client-side role filtering and server-side validation to prevent bypass attacks.
- **Timezone Standardization**: All datetime operations, database timestamps, audit trails, and user-facing displays use Jamaica Standard Time (UTC-05:00) consistently.

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