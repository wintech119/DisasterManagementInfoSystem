# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (November 21, 2025)
- **Identified Technical Limitation for LO Read-Only Enforcement**: Discovered that read-only restrictions for Logistics Officers after package submission cannot be implemented without database schema changes. Both `_save_draft()` and `_submit_for_approval()` workflows set identical fields (relief_pkg.status_code='P', relief_pkg.update_by_id), making it impossible to distinguish draft packages (which LOs should still be able to edit) from submitted packages (which should be read-only for LOs). The existing schema lacks a reliable marker to differentiate these two states. Implementing this feature would require adding a new field (e.g., `submitted_for_approval_dtime`, a boolean flag, or repurposing `verify_by_id`) to track submission state independently from draft saves. This constraint prevents enforcement of read-only restrictions while preserving the "no schema changes" requirement.
- **Fixed Awaiting Approval Tab Filtering for LOs**: Corrected tab filtering logic to ensure packages with "Awaiting Approval" status appear in the correct tab for Logistics Officers instead of showing under "Being Prepared". Fixed `has_pending_approval()` to detect submitted packages by checking relief request status (PART_FILLED) instead of verify_by_id field, since verify_by_id is only set by LM during approval. Updated `is_user_involved()` to include relief request creator check. Tab transitions now correctly reflect workflow states: Draft (SUBMITTED + pkg status='P') → Being Prepared; Submitted (PART_FILLED + pkg status='P') → Awaiting Approval; Approved (pkg status='D') → Approved for Dispatch.
- **Comprehensive Optimistic Locking for Relief Package Workflow**: Implemented full optimistic locking across all relief package preparation and approval workflows to prevent lost updates in multi-user scenarios. Added `_validate_version_nbr()` helper function and integrated version validation in:
  - **Preparation Workflow** (`prepare_package` route): `_save_draft()`, `_submit_for_approval()`, `_send_for_dispatch()` - validates both relief request and package version numbers before any mutations
  - **Approval Workflow** (`approve_package` route): `_save_draft_approval()`, `_approve_and_dispatch()` - validates versions before LM modifications
  - **Templates**: `prepare.html` and `approve.html` now include hidden `version_nbr` fields for both relief request and package
  - **Error Handling**: All OptimisticLockError exceptions are caught and display user-friendly messages ("This [entity] has been updated by another user. Please refresh and try again."), with automatic rollback to prevent partial saves
  - **Multi-user Safety**: Prevents lost updates when multiple users (LO vs LO, LO vs LM, LM vs LM) attempt to modify the same relief request or package simultaneously
- **Submit-Once Guard for Relief Request Approval**: Implemented prevention of duplicate submissions to Logistics Managers. Only one Logistics Officer can submit a relief request for LM approval; subsequent attempts by other LOs are blocked with a clear message: "This relief request has already been submitted to the Logistics Manager for approval by another user." Uses existing `status_code='P'` and `verify_by_id` fields plus `version_nbr` optimistic locking to handle race conditions where multiple LOs attempt simultaneous submission. No database schema changes required.
- **Enhanced Package Visibility for LOs**: Fixed filtering logic in "Approved for Dispatch" and "Approved (No Allocation)" tabs to ensure Logistics Officers can see packages tied to relief requests they created, in addition to packages they directly created or updated. This ensures LOs who create relief requests can see the full lifecycle of those requests through approval and dispatch.
- **Status Dropdown Logic on Prepare Relief Package Page**: Implemented automatic status dropdown behavior based on allocation quantities for both LO and LM roles. The system now enforces three cases: (1) Fully Allocated (Allocated == Requested) automatically sets status to "FILLED" and locks the dropdown as read-only; (2) No Allocation (Allocated == 0) defaults to "UNAVAILABLE" with options for UNAVAILABLE, DENIED, and AWAITING AVAILABILITY; (3) Partially Allocated (0 < Allocated < Requested) defaults to "PARTLY FILLED" with options for PARTLY FILLED and ALLOWED LIMIT. Status and options automatically refresh after closing the batch allocation drawer, ensuring dropdown always reflects current allocation state.
- **Badge Counts Visibility**: Removed all queue/badge counts from workflow tabs for Logistics Officers (e.g., "Approved for Dispatch" without any number). Logistics Managers continue to see global badge counts for supervisory oversight (e.g., "Approved for Dispatch (6)"). This simplifies the interface for LOs while maintaining full visibility for LMs across all workflow tabs.
- **Awaiting Approval Tab Access for LOs**: Extended "Awaiting Approval" tab access to both Logistics Officers and Logistics Managers. LOs can now view all packages they submitted for approval, while LMs continue to see all packages from all LOs. Updated navigation to show the tab and summary card for both roles. This improves workflow visibility and allows LOs to track their submitted packages through the approval process.

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
-   **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Features secure user management with role assignment restrictions to prevent privilege escalation: CUSTODIAN users can manage operational users but cannot assign administrative roles (SYSTEM_ADMINISTRATOR, SYS_ADMIN); includes both client-side role filtering and server-side validation to prevent bypass attacks.
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