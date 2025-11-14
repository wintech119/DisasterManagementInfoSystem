# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the full lifecycle of disaster relief supplies. It ensures compliance with government processes using the `aidmgmt-3.sql` schema. The system streamlines inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, supporting disaster event coordination and supply allocation. It includes user administration with RBAC, donor/agency/custodian management, inventory transfers, location tracking, analytics, reporting, and robust security features.

**Key Achievements (Phases 1-8 Complete - November 14, 2025):**
- ✅ Comprehensive role-based access control with 26 features mapped to 10 verified database roles
- ✅ 6 specialized dashboards with modern UI for different user roles
- ✅ Dynamic navigation system that adapts to user permissions
- ✅ User profile pages with role-specific feature visibility
- ✅ Backend security decorators for route protection
- ✅ Complete testing infrastructure with test accounts and documentation
- ✅ Consistent modern UI across all pages matching GOJ branding

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
All pages maintain a modern, consistent UI matching Relief Package preparation pages, characterized by:
- **Consistent Styling**: Modern UI standard with summary metric cards, filter tabs, modern tables (`relief-requests-table`), standardized action buttons (`btn-relief-primary`, `btn-relief-secondary`), color-coded status badges, and clean layouts.
- **Shared Components**: Reusable Jinja2 macros for status badges, summary cards, and a unified workflow progress sidebar (`_workflow_progress.html`).
- **Styling**: Uses `relief-requests-ui.css` and `workflow-sidebar.css` for global consistency.
- **Responsiveness**: Fixed header, collapsible sidebar, dynamic content margins.
- **Branding**: GOJ branding with primary green and gold accent, official logos, and accessibility features.
- **Workflows**: Standardized 5-step workflow patterns for Agency Relief Requests and Eligibility Approval.
- **Package Fulfillment Workflow**: Modern UI with real-time calculations, multi-warehouse allocation, dynamic item status validation, and inventory reservation.
- **Dashboard System**: 6 role-specific dashboards with consistent modern UI, filter tabs, summary cards, and optimized queries.

### Database Architecture
- **Schema**: Based on the authoritative ODPEM `aidmgmt-3.sql` schema (40 tables).
- **Key Design Decisions**:
    - **Data Consistency**: All `varchar` fields in uppercase.
    - **Auditability**: `create_by_id`, `create_dtime`, `version_nbr` standard on all ODPEM tables.
    - **Precision**: `DECIMAL(15,4)` for quantity fields.
    - **Status Management**: Integer/character codes for entity statuses, with lookup tables.
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col`.
    - **User Management**: Enhanced `public.user` table with MFA, lockout, password management, agency linkage, and `citext` for case-insensitive email.
    - **New Workflows**: `agency_account_request` and `agency_account_request_audit` tables for account creation workflows.

### Data Flow Patterns
- **AIDMGMT Relief Workflow**: End-to-end process from request creation (agencies) to eligibility review (ODPEM directors), package preparation (logistics), and distribution.
- **Dashboards**: Role-based dashboard routing with 6 specialized views (Logistics, Agency, Director, Admin, Inventory, General). Main dashboard (`/`) automatically routes users based on primary role.
- **Inventory Management**: Tracks stock by warehouse and item in the `inventory` table, including `usable_qty`, `reserved_qty`, `defective_qty`, `expired_qty`, with bin-level tracking.
- **Eligibility Approval Workflow**: Role-based access control (RBAC) and service layer for eligibility decisions.
- **Package Fulfillment Workflow**: Unified `packaging` blueprint with routes for pending fulfillment and package preparation. Includes features like summary metric cards, multi-warehouse allocation, dynamic item status validation, and a 4-step workflow sidebar.
- **Services**: `ItemStatusService` for status validation and `InventoryReservationService` for transaction-safe inventory reservation.

### Role-Based Access Control (RBAC)
- **Feature Registry**: Centralized feature-to-role mapping in `app/core/feature_registry.py` with 26 features mapped to 10 verified database role codes.
- **Dynamic Navigation System**: Role-based dynamic navigation (`templates/components/_dynamic_navigation.html`) adapts to user permissions, showing only accessible features.
- **Security Decorators**: Backend route protection decorators (`app/core/decorators.py`) for single, any, or all feature access control.
- **Smart Routing**: Automatic dashboard routing based on user's primary role.
- **Role Priority**: SYSTEM_ADMINISTRATOR > ODPEM_DG/DDG/DIR_PEOD > LOGISTICS_MANAGER > LOGISTICS_OFFICER > INVENTORY_CLERK > AGENCY_DISTRIBUTOR/SHELTER.
- **Verified Database Roles**: SYSTEM_ADMINISTRATOR, LOGISTICS_MANAGER, LOGISTICS_OFFICER, ODPEM_DG, ODPEM_DDG, ODPEM_DIR_PEOD, INVENTORY_CLERK, AGENCY_DISTRIBUTOR, AGENCY_SHELTER, AUDITOR.

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

### Database Schema and Initialization
- **DRIMS_Complete_Schema.sql**: For initial database setup and seeding reference data.
- `scripts/init_db.py`: Executes the complete schema.
- `scripts/seed_demo.py`: Populates minimal test data.