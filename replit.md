# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the full lifecycle of disaster relief supplies. It ensures compliance with government processes using the `aidmgmt-3.sql` schema. The system streamlines inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, supporting disaster event coordination and supply allocation. It includes robust user administration with RBAC, comprehensive management of donors, agencies, and custodians, inventory transfers, location tracking, analytics, reporting, and strong security features. The project aims to provide a modern, efficient, and user-friendly system for disaster preparedness and response.

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
All pages maintain a modern, consistent UI with a comprehensive design system:
- **Modern Design System** (`modern-ui.css`): Foundation with 50+ CSS custom properties for colors, spacing, typography, shadows, border radius values, and z-index scale. Includes a complete component library with metric cards, filter tabs, modern tables, buttons, status badges, alerts, forms, empty states, loading spinners, login page components, and standardized checkboxes (20px × 20px with proper spacing).
- **Consistent Styling**: Modern UI standard with summary metric cards, filter tabs, modern tables (`modern-table`), standardized action buttons (`btn-modern`, `btn-primary`, `btn-outline`), color-coded status badges, code/SKU pills (`code-pill`), standardized checkboxes with 0.75rem spacing from labels, and clean page layouts.
- **Shared Components**: Reusable Jinja2 macros for status badges, summary cards, and a unified workflow progress sidebar (`_workflow_progress.html`). All components use design tokens for maintainability.
- **Styling**: Uses `modern-ui.css` (foundation), `relief-requests-ui.css`, `notifications-ui.css`, `user-management-ui.css`, and `workflow-sidebar.css` for feature-specific enhancements.
- **Responsiveness**: Fixed header, collapsible sidebar, dynamic content margins, responsive grid layouts with Bootstrap 5.3.3.
- **Branding**: GOJ branding with primary green (#009639) and gold accent (#FDB913), official Jamaica Coat of Arms and ODPEM logos, consistent across all pages.
- **Accessibility**: WCAG 2.1 AA compliance with focus-visible states, proper color contrast, ARIA labels, semantic HTML, and screen reader support.
- **Workflows**: Standardized 5-step workflow patterns for Agency Relief Requests and Eligibility Approval.
- **Dashboard System**: 6 role-specific dashboards with consistent modern UI, filter tabs, summary cards, and optimized queries. System Administration dashboard features modern tables with status badges, enhanced quick links with modern buttons, and improved recent users display with avatars.
- **Management Modules**: Comprehensive modules for Event Management, Warehouse Management, User Management, Notification Management, Item Management, Item Category Management, Custodian Management, Unit of Measure Management, Batch Management, and Inventory, all featuring modern UI, CRUD operations, validation, and optimistic locking. All Create forms follow a consistent structure with sectioned layouts, icon headers, proper spacing, and standardized action buttons.

### Database Architecture
- **Schema**: Based on the authoritative ODPEM `aidmgmt-3.sql` schema (40 tables).
- **Key Design Decisions**:
    - **Data Consistency**: All `varchar` fields in uppercase.
    - **Auditability**: Standard `create_by_id`, `create_dtime`, `version_nbr` on all ODPEM tables. Audit fields now use `user.user_name` (varchar(20)) for consistent tracking.
    - **Precision**: `DECIMAL(15,4)` for quantity fields.
    - **Status Management**: Integer/character codes for entity statuses, with lookup tables.
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col`.
    - **User Management**: Enhanced `public.user` table with `user_name` field, MFA, lockout, password management, agency linkage, and `citext` for case-insensitive email.
    - **New Workflows**: `agency_account_request` and `agency_account_request_audit` tables for account creation workflows.
    - **Phone Number Format**: System-wide standardization to `+1 (XXX) XXX-XXXX` format with centralized validation (`app/core/phone_utils.py`) and auto-formatting masked input (`static/js/phone-mask.js`).
    - **Warehouse Types**: Simplified to two types only: `MAIN-HUB` (central/main warehouses) and `SUB-HUB` (sub-warehouses, agency warehouses). Database check constraint enforces these values only.
    - **Item Category Schema**: Updated `itemcatg` table to use `category_id` (integer identity) as primary key instead of `category_code`. The `category_code` remains as a unique business key with uppercase check constraint. Includes `status_code` ('A'/'I') and full optimistic locking support.
    - **Custodian Table**: Migrated to DRIMS naming standards with constraints: `pk_custodian` (primary key), `uk_custodian_1` (unique custodian_name), `c_custodian_1` (uppercase custodian_name check), `c_custodian_3` (uppercase contact_name check), `fk_custodian_parish` (foreign key to parish). Identity column for `custodian_id`, timestamp(0) precision for audit fields.
    - **Item Table Schema**: Migrated to target specifications with proper constraints and column ordering. Primary key renamed to `pk_item`, unique constraints `uk_item_1` (item_code), `uk_item_2` (item_name), `uk_item_3` (sku_code). Added 5 new columns: `item_code` (position 2, varchar(30) unique), `units_size_vary_flag`, `is_batched_flag`, `can_expire_flag`, `issuance_order` (FIFO/LIFO/FEFO). Removed obsolete columns: `category_code`, `expiration_apply_flag`. All varchar fields enforce uppercase. Full optimistic locking support via `version_nbr`.
    - **Batch Tracking System**: New `itembatch` table supports batch-level inventory management with FEFO/FIFO allocation rules. Features include: batch number tracking (uppercase), batch/expiry dates, batch-level quantities (usable/reserved/defective/expired using DECIMAL(15,4)), UOM tracking, size specifications, avg_unit_value, verification tracking, status codes (A/U), and full optimistic locking. Indexes support FEFO (expiry_date) and FIFO (batch_date) queries. The `reliefpkg_item` table now includes REQUIRED `batch_id` as part of composite primary key (reliefpkg_id, fr_inventory_id, item_id, batch_id) to enforce mandatory batch-level allocation tracking. SQLAlchemy relationships use explicit `primaryjoin` conditions to handle composite foreign keys.
    - **Inventory Table Schema**: Migrated to target specifications with composite primary key (inventory_id, item_id) where inventory_id IS the warehouse_id. No separate warehouse_id column - inventory_id references warehouse(warehouse_id) for alignment. `inventory_id` is integer NOT NULL (not auto-generated) and must be manually set to match warehouse_id when creating records. Includes reorder_qty column, named constraints (c_inventory_1 through c_inventory_7), conditional unique index uk_inventory_1 on (item_id, inventory_id) WHERE usable_qty > 0, and duplicate index dk_inventory_1 on item_id for join optimization. Single-column foreign keys to inventory_id reference warehouse(warehouse_id) since inventory_id is not unique (composite PK model). All code updated to use `inventory.inventory_id` instead of removed `inventory.warehouse_id` field.

### Data Flow Patterns
- **AIDMGMT Relief Workflow**: End-to-end process from request creation (agencies) to eligibility review (ODPEM directors), package preparation (logistics), and distribution.
- **Dashboards**: Role-based dashboard routing with 6 specialized views (Logistics, Agency, Director, Admin, Inventory, General). Main dashboard (`/`) automatically routes users based on primary role.
- **Inventory Management**: Two-tier tracking system: warehouse-level stock in `inventory` table (usable/reserved/defective/expired quantities) and batch-level tracking in `itembatch` table for items with `is_batched_flag=TRUE`. Batch allocation supports FEFO (First Expired First Out) for expirable items and FIFO (First In First Out) for non-expirable items based on `item.issuance_order` configuration.
- **Eligibility Approval Workflow**: Role-based access control (RBAC) and service layer for eligibility decisions.
- **Package Fulfillment Workflow**: Unified `packaging` blueprint with routes for pending fulfillment and package preparation. Includes features like summary metric cards, multi-warehouse allocation, dynamic item status validation, and a 4-step workflow sidebar.
- **Services**: `ItemStatusService` for status validation, `InventoryReservationService` for transaction-safe inventory reservation, and `BatchAllocationService` for automatic FEFO/FIFO batch allocation with configurable issuance order rules.

### Role-Based Access Control (RBAC)
- **Feature Registry**: Centralized feature-to-role mapping in `app/core/feature_registry.py` with 26 features mapped to 10 verified database role codes.
- **Dynamic Navigation System**: Role-based dynamic navigation (`templates/components/_dynamic_navigation.html`) adapts to user permissions.
- **Security Decorators**: Backend route protection decorators (`app/core/decorators.py`) for single, any, or all feature access control.
- **Smart Routing**: Automatic dashboard routing based on user's primary role.
- **Role Priority**: SYSTEM_ADMINISTRATOR > ODPEM_DG/DDG/DIR_PEOD > CUSTODIAN > LOGISTICS_MANAGER > LOGISTICS_OFFICER > INVENTORY_CLERK > AGENCY_DISTRIBUTOR/SHELTER.
- **Verified Database Roles**: SYSTEM_ADMINISTRATOR, LOGISTICS_MANAGER, LOGISTICS_OFFICER, ODPEM_DG, ODPEM_DDG, ODPEM_DIR_PEOD, INVENTORY_CLERK, AGENCY_DISTRIBUTOR, AGENCY_SHELTER, AUDITOR, CUSTODIAN.
- **Master Data RBAC Restrictions**: Event, Warehouse, Item, ItemCategory, UnitOfMeasure, and Custodian table CRUD operations restricted to CUSTODIAN role only. Master data tables follow consistent naming standards for constraints (pk_, uk_, c_, fk_ prefixes).
- **Item Management Module**: Full CRUD operations for relief items (`app/features/items.py`) restricted to CUSTODIAN role. Features include search/filter by category, batch tracking, expiration tracking, status tabs (Active/Inactive/Batched/Expirable), summary metrics, validation helpers for item_code/item_name/sku_code/reorder_qty/issuance_order/comments, uniqueness checks, optimistic locking, stock/transaction checks before inactivation, and modern UI templates (list, create, view, edit) following established design patterns.
- **Batch Management Module**: Full CRUD operations for item batches (`app/features/batches.py`) restricted to CUSTODIAN role via MASTER_DATA_MGMT feature. Features include: list view with filter tabs (Active/Expiring Soon/Expired/Unavailable/All), search by batch number/item name, warehouse and item filters, summary metrics (total batches, active, expiring soon, expired, available qty), batch creation with validation, batch view with audit information, batch editing with optimistic locking, expiry date tracking with visual indicators for expired/expiring soon batches, quantity management (usable/reserved/defective/expired), verification flag, size specification, average unit value tracking, and modern UI templates following established design patterns. API endpoint for batch lookup by item/warehouse for dropdown population.

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
```