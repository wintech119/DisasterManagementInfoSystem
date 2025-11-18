# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the full lifecycle of disaster relief supplies. It aims to streamline inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, ensuring compliance with government processes. The system supports disaster event coordination, supply allocation, user administration with RBAC, and comprehensive management of various entities, inventory transfers, location tracking, analytics, and reporting. The project's ambition is to provide a modern, efficient, and user-friendly system for disaster preparedness and response, ensuring robust security features.

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

### Application Structure
- **Modular Blueprint Architecture**: Feature-specific blueprints under `app/features/`.
- **Database-First Approach**: SQLAlchemy models map to a pre-existing ODPEM `aidmgmt-3.sql` schema.
- **Shared Utilities**: Located in `app/core/`.
- **Templates**: Jinja2 templates (`templates/`) enforce Government of Jamaica (GOJ) branding.

### UI/UX Design
All pages maintain a modern, consistent UI with a comprehensive design system including:
- **Modern Design System**: Foundation with 50+ CSS custom properties, a complete component library, and standardized checkboxes.
- **Consistent Styling**: Modern UI standard with summary metric cards, filter tabs, modern tables, standardized action buttons, color-coded status badges, and clean page layouts.
- **Shared Components**: Reusable Jinja2 macros for status badges, summary cards, and a unified workflow progress sidebar.
- **Responsiveness**: Fixed header, collapsible sidebar, dynamic content margins, responsive grid layouts with Bootstrap 5.3.3.
- **Branding**: GOJ branding with primary green (#009639) and gold accent (#FDB913), official Jamaica Coat of Arms and ODPEM logos.
- **Accessibility**: WCAG 2.1 AA compliance with focus-visible states, proper color contrast, ARIA labels, semantic HTML, and screen reader support.
- **Workflows**: Standardized 5-step workflow patterns for Agency Relief Requests and Eligibility Approval.
- **Dashboards**: 6 role-specific dashboards with consistent modern UI, filter tabs, and summary cards.
- **Management Modules**: Comprehensive modules for Event, Warehouse, User, Notification, Item, Item Category, Custodian, Unit of Measure, Inventory, and Donation management, all featuring modern UI, CRUD operations, validation, and optimistic locking.
- **Notification System**: Real-time in-app notifications with bell icon badge counter, offcanvas panel, deep-linking to relevant pages, and read/unread tracking. Features: (1) NEW tag displays for unread notifications, (2) Click-to-mark-as-read functionality with optimistic UI updates, (3) Badge count updates immediately before navigation, (4) Event delegation prevents duplicate listeners, (5) Automatic badge refresh every 30 seconds, (6) "Mark All Read" and "Clear All" bulk operations.
- **Donation Processing**: Complete donation workflow including header and item management, status tracking (Entered, Verified, Processed), automatic verification on acceptance, modern UI with summary cards and filter tabs, restricted to LOGISTICS_MANAGER and LOGISTICS_OFFICER roles. Donation creation form uses consistent modern UI pattern matching warehouse management and agency relief request pages, with inline item addition following agency request items edit page interaction pattern. Auto-verification workflow ensures all accepted donations are immediately verified within the same transaction (no separate verification step).
- **Donation Intake Management**: Full workflow for intaking verified donations into warehouse inventory. Features: (1) Select verified donations (status='V') and target warehouse, (2) Batch-level tracking with mandatory batch numbers for batched items, (3) Expiry date management for perishable items, (4) Split quantities (usable, defective, expired), (5) Atomic transaction creates dnintake header/items, itembatch records, updates inventory totals, and marks donation as Processed, (6) Quantity validation ensures intake matches donation exactly (database-sourced), (7) Concurrency control with SELECT FOR UPDATE on inventory, (8) MVP: No updates to existing intakes (prevents duplicate processing), (9) Modern UI with filter tabs, summary cards, and comprehensive validation feedback, (10) Restricted to LOGISTICS_MANAGER and LOGISTICS_OFFICER roles, (11) YYYY-MM-DD date format enforcement via Flatpickr library on all date fields (intake_date, batch_date, expiry_date) with calendar picker functionality and min/max validation, (12) DonationIntake model includes warehouse relationship via explicit primaryjoin for template access to warehouse details, (13) Batch number uniqueness validation prevents duplicate batch numbers for the same item with user-friendly error messages (auto-generated NOBATCH placeholders for non-batched items are excluded from validation).

### Database Architecture
- **Schema**: Based on the authoritative ODPEM `aidmgmt-3.sql` schema (40 tables).
- **Key Design Decisions**:
    - **Data Consistency**: All `varchar` fields in uppercase.
    - **Auditability**: Standard `create_by_id`, `create_dtime`, `version_nbr` on all ODPEM tables.
    - **Precision**: `DECIMAL(15,4)` for quantity fields.
    - **Status Management**: Integer/character codes for entity statuses, with lookup tables.
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col`.
    - **User Management**: Enhanced `public.user` table with `user_name`, MFA, lockout, password management, agency linkage, and `citext` for case-insensitive email.
    - **Batch Tracking System**: New `itembatch` table supports batch-level inventory management with FEFO/FIFO allocation rules, integrated with `reliefpkg_item` for mandatory batch-level allocation.
    - **Inventory Table Schema**: Composite primary key (inventory_id, item_id) where inventory_id represents the warehouse_id, supporting batch-level inventory tracking.
    - **Relief Request Status Table**: 10 status codes (0-9) organized into three workflow views with reason requirements for DENIED, CLOSED, and INELIGIBLE statuses.
    - **Relief Package Table**: Tracks relief packages with agency_id, tracking_no (7-char), eligible_event_id, and 6 status codes (A=Draft, P=Processing, C=Completed, V=Verified, D=Dispatched, R=Received).
    - **Atomic Transaction Workflow**: Implemented for donation creation, ensuring header and all items are saved in a single transaction or none at all.
    - **Donation Item Status**: Default value 'V' (Verified) set at database and model level for `donation_item.status_code`, removed from form UI for streamlined user experience.
    - **Auto-Verification on Acceptance (MVP)**: Donations and donation items are automatically verified during the acceptance transaction. `verify_by_id` and `verify_dtime` are set to match `create_by_id` and `create_dtime`. Donation headers receive status 'V' (Verified) on creation. No separate verification workflow or UI elements exist in MVP. All updates that pass validation maintain verified status with updated verification timestamps.

### Data Flow Patterns
- **AIDMGMT Relief Workflow**: End-to-end process from request creation to distribution.
- **Dashboards**: Role-based dashboard routing with 6 specialized views.
- **Inventory Management**: Two-tier tracking system: warehouse-level stock and batch-level tracking with FEFO/FIFO allocation.
- **Eligibility Approval Workflow**: Role-based access control and service layer for eligibility decisions.
- **Package Fulfillment Workflow**: Unified `packaging` blueprint with routes for pending fulfillment and package preparation.
- **Services**: `ItemStatusService`, `InventoryReservationService`, and `BatchAllocationService`.
- **Donation Processing Workflow**: Complete CRUD operations for donation headers and items with status transitions, verification tracking, and inventory integration.

### Role-Based Access Control (RBAC)
- **Feature Registry**: Centralized feature-to-role mapping in `app/core/feature_registry.py` (27 features to 10 database roles).
- **Dynamic Navigation System**: Role-based dynamic navigation (`templates/components/_dynamic_navigation.html`).
- **Security Decorators**: Backend route protection decorators (`app/core/decorators.py`).
- **Smart Routing**: Automatic dashboard routing based on user's primary role.
- **Role Priority**: Defined hierarchy from SYSTEM_ADMINISTRATOR to AGENCY_DISTRIBUTOR/SHELTER.
- **Verified Database Roles**: SYSTEM_ADMINISTRATOR, LOGISTICS_MANAGER, LOGISTICS_OFFICER, ODPEM_DG, ODPEM_DDG, ODPEM_DIR_PEOD, INVENTORY_CLERK, AGENCY_DISTRIBUTOR, AGENCY_SHELTER, AUDITOR, CUSTODIAN.
- **Master Data RBAC Restrictions**: CRUD operations for Event, Warehouse, Item, ItemCategory, UnitOfMeasure, and Custodian restricted to CUSTODIAN role.
- **Item Management Module**: Full CRUD for relief items restricted to CUSTODIAN role.
- **Automatic Batch Creation**: Batches are automatically created during inventory intake processes for items with `is_batched_flag=TRUE` via `BatchCreationService`.

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
- Flatpickr (latest) - ISO date picker for YYYY-MM-DD format enforcement