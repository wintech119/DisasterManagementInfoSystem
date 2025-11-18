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
- **Database-First Approach**: SQLAlchemy models (`app/db/models.py`) map to a pre-existing ODPEM `aidmgmt-3.sql` schema.
- **Shared Utilities**: Located in `app/core/`.
- **Templates**: Jinja2 templates (`templates/`) enforce Government of Jamaica (GOJ) branding.

### UI/UX Design
All pages maintain a modern, consistent UI with a comprehensive design system including:
- **Modern Design System**: Foundation with 50+ CSS custom properties, a complete component library (metric cards, filter tabs, modern tables, buttons, status badges, alerts, forms, empty states, loading spinners), and standardized checkboxes.
- **Consistent Styling**: Modern UI standard with summary metric cards, filter tabs, modern tables, standardized action buttons, color-coded status badges, and clean page layouts.
- **Shared Components**: Reusable Jinja2 macros for status badges, summary cards, and a unified workflow progress sidebar.
- **Responsiveness**: Fixed header, collapsible sidebar, dynamic content margins, responsive grid layouts with Bootstrap 5.3.3.
- **Branding**: GOJ branding with primary green (#009639) and gold accent (#FDB913), official Jamaica Coat of Arms and ODPEM logos.
- **Accessibility**: WCAG 2.1 AA compliance with focus-visible states, proper color contrast, ARIA labels, semantic HTML, and screen reader support.
- **Workflows**: Standardized 5-step workflow patterns for Agency Relief Requests and Eligibility Approval.
- **Dashboards**: 6 role-specific dashboards with consistent modern UI, filter tabs, and summary cards.
- **Management Modules**: Comprehensive modules for Event, Warehouse, User, Notification, Item, Item Category, Custodian, Unit of Measure, and Inventory management, all featuring modern UI, CRUD operations, validation, and optimistic locking.

### Database Architecture
- **Schema**: Based on the authoritative ODPEM `aidmgmt-3.sql` schema (40 tables).
- **Key Design Decisions**:
    - **Data Consistency**: All `varchar` fields in uppercase.
    - **Auditability**: Standard `create_by_id`, `create_dtime`, `version_nbr` on all ODPEM tables.
    - **Precision**: `DECIMAL(15,4)` for quantity fields.
    - **Status Management**: Integer/character codes for entity statuses, with lookup tables.
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col`.
    - **User Management**: Enhanced `public.user` table with `user_name`, MFA, lockout, password management, agency linkage, and `citext` for case-insensitive email.
    - **New Workflows**: `agency_account_request` and `agency_account_request_audit` tables for account creation.
    - **Phone Number Format**: System-wide standardization to `+1 (XXX) XXX-XXXX`.
    - **Donation Table**: Tracks donations with status workflow (Entered, Verified, Processed).
    - **Donation Item Table**: Links donations to specific items with quantities, UOM, location, and verification status (Processed, Verified).
    - **Donation Intake Tables**: Two-table system - `dnintake` for intake headers and `dnintake_item` for batch-level intake tracking with status codes (Processed, Verified).
    - **Warehouse Types**: Simplified to two types: `MAIN-HUB` and `SUB-HUB`.
    - **Item Category Schema**: `itemcatg` uses `category_id` (integer identity) as primary key.
    - **Custodian Table**: Migrated to DRIMS naming standards.
    - **Item Table Schema**: Includes `item_code`, `units_size_vary_flag`, `is_batched_flag`, `can_expire_flag`, `issuance_order` (FIFO/LIFO/FEFO).
    - **Batch Tracking System**: New `itembatch` table supports batch-level inventory management with FEFO/FIFO allocation rules. The `reliefpkg_item` table now includes `batch_id` as part of its composite primary key for mandatory batch-level allocation tracking.
    - **Inventory Table Schema**: Composite primary key (inventory_id, item_id) where inventory_id is the warehouse_id.
    - **Event Table Schema**: Uses `GENERATED BY DEFAULT AS IDENTITY` for `event_id`. Supports 10 event types.
    - **Transfer Table**: Tracks inventory transfers between warehouses with eligible_event_id and status workflow (Draft, Completed, Verified, Processed).
    - **Relief Request Status Table**: 10 status codes (0-9) organized into three workflow views (create, action, processed) with reason requirements for DENIED, CLOSED, and INELIGIBLE statuses.
    - **Relief Package Table**: Tracks relief packages with agency_id, tracking_no (7-char), eligible_event_id, and 6 status codes (A=Draft, P=Processing, C=Completed, V=Verified, D=Dispatched, R=Received) with dispatch datetime constraint.
    - **Relief Request Item Constraint c_reliefrqst_item_2a**: Enforces status-based issue_qty rules - R/U/W/D statuses require issue_qty=0, P/L statuses require issue_qty<request_qty, F status requires issue_qty=request_qty.

### Data Flow Patterns
- **AIDMGMT Relief Workflow**: End-to-end process from request creation to distribution.
- **Dashboards**: Role-based dashboard routing with 6 specialized views.
- **Inventory Management**: Two-tier tracking system: warehouse-level stock and batch-level tracking with FEFO/FIFO allocation.
- **Eligibility Approval Workflow**: Role-based access control and service layer for eligibility decisions.
- **Package Fulfillment Workflow**: Unified `packaging` blueprint with routes for pending fulfillment and package preparation.
- **Services**: `ItemStatusService`, `InventoryReservationService`, and `BatchAllocationService`.

### Role-Based Access Control (RBAC)
- **Feature Registry**: Centralized feature-to-role mapping in `app/core/feature_registry.py` (26 features to 10 database roles).
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