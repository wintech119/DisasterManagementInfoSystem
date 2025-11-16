# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the full lifecycle of disaster relief supplies. It ensures compliance with government processes using the `aidmgmt-3.sql` schema. The system streamlines inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, supporting disaster event coordination and supply allocation. It includes user administration with RBAC, donor/agency/custodian management, inventory transfers, location tracking, analytics, reporting, and robust security features.

**Key Achievements (Phases 1-12 Complete - November 16, 2025):**
- ✅ Comprehensive role-based access control with 26 features mapped to 10 verified database roles
- ✅ 6 specialized dashboards with modern UI for different user roles
- ✅ Dynamic navigation system that adapts to user permissions
- ✅ User profile pages with role-specific feature visibility
- ✅ Backend security decorators for route protection
- ✅ Complete testing infrastructure with test accounts and documentation
- ✅ **System-wide modern UI design system** (`modern-ui.css`) with 50+ design tokens (colors, spacing, typography, shadows), reusable component classes (metric cards, filter tabs, modern tables, buttons, badges, alerts, forms, empty states), login page styles, and code/SKU pill components - all using CSS custom properties for maintainability
- ✅ **Modernized login page** with GOJ branding, responsive design, Bootstrap integration (removed Tailwind), and agency account request CTA
- ✅ **Modernized landing dashboard** (`index.html`) with modern metric cards, consistent layout, and quick action buttons
- ✅ **Modernized inventory module** list page with filter bar, modern tables, code pills, and empty states
- ✅ **Modernized items module** list page with filter tabs, modern tables, status badges, and empty states
- ✅ **Items Create page** enhanced with "Other (specify)" UOM option: dropdown selection with automatic custom UOM field reveal, client-side validation (2-20 characters, alphanumeric + special chars), server-side validation, automatic `unitofmeasure` table entry creation for custom values, no database schema changes required
- ✅ **Modernized warehouses module** list page with filter tabs, modern tables, and empty states
- ✅ Notification system complete redesign with modern UI matching user management patterns: 6 metric cards, filter tabs (All/Unread/Read/Today/This Week/Low Stock), reusable macros for notification cards and icons, dedicated CSS file (notifications-ui.css), offcanvas bell dropdown with dynamic loading, clear all modal, individual delete functionality, and WCAG 2.1 AA accessibility features
- ✅ User management complete redesign with modern UI, metrics dashboard, tabbed profiles, security indicators, and accessibility features
- ✅ User model enhanced with `is_locked` property and compatibility aliases for template field names
- ✅ **Event Management Module Complete** (November 16, 2025): Full CRUD operations for disaster events with CUSTODIAN role support, 5 EVENT permissions (CREATE/VIEW/UPDATE/DELETE/CLOSE), comprehensive validation (8 event types, date constraints, status transitions), optimistic locking with `version_nbr` and row-level locking (`with_for_update()`), closed event immutability enforcement, FK deletion checks, audit trail tracking, and WCAG 2.1 AA accessibility compliance
- ✅ **Event Management UI Standardization** (November 16, 2025): Complete UI redesign matching Relief Request/Package workflow templates - all 4 Event templates (list/create/edit/view) now use `relief-requests-ui.css`, summary metric cards (Total/Active/Closed), filter tabs (All/Active/Closed), integrated search bar, modern table design, card-based form layouts, btn-relief-* button classes throughout, audit sidebar in detail view, empty states with contextual CTAs, and navigation placement under OPERATIONS category for consistency with relief workflows
- ✅ **Audit Trail Enhancement with user_name Field** (November 16, 2025): System-wide `user_name` field (varchar(20), NOT NULL) for consistent audit trail tracking - replaces email truncation with dedicated user identifier, auto-generated from email during user creation, server-side validation with [:20] truncation enforcement, real-time character counter (0/20) with visual feedback, integrated across all add_audit_fields calls (events, items, warehouses, custom UOMs, etc.), and database migration completed for all 13 existing users

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
- **Modern Design System** (`modern-ui.css`): Foundation with 50+ CSS custom properties for colors (primary greens, semantic colors, neutrals, tinted backgrounds), spacing (0.25rem to 2.5rem), typography (9 font sizes, 4 weights), shadows (5 levels), border radius values, and z-index scale. Includes complete component library with metric cards, filter tabs, modern tables, buttons (6 variants + sizes), status badges, alerts, forms, empty states, loading spinners, and login page components.
- **Consistent Styling**: Modern UI standard with summary metric cards, filter tabs, modern tables (`modern-table`), standardized action buttons (`btn-modern`, `btn-primary`, `btn-outline`), color-coded status badges (`status-badge-success`, `status-badge-warning`), code/SKU pills (`code-pill`), and clean page layouts (`page-container`, `page-header-modern`).
- **Shared Components**: Reusable Jinja2 macros for status badges, summary cards, and a unified workflow progress sidebar (`_workflow_progress.html`). All components use design tokens for maintainability.
- **Styling**: Uses `modern-ui.css` (foundation), `relief-requests-ui.css`, `notifications-ui.css`, `user-management-ui.css`, and `workflow-sidebar.css` for feature-specific enhancements.
- **Responsiveness**: Fixed header, collapsible sidebar, dynamic content margins, responsive grid layouts with Bootstrap 5.3.3.
- **Branding**: GOJ branding with primary green (#009639) and gold accent (#FDB913), official Jamaica Coat of Arms and ODPEM logos, consistent across all pages.
- **Accessibility**: WCAG 2.1 AA compliance with focus-visible states, proper color contrast (4.5:1 for text), ARIA labels, semantic HTML, and screen reader support.
- **Workflows**: Standardized 5-step workflow patterns for Agency Relief Requests and Eligibility Approval.
- **Package Fulfillment Workflow**: Modern UI with real-time calculations, multi-warehouse allocation (filtered to show only warehouses with active stock for each item), dynamic item status validation, and inventory reservation.
- **Dashboard System**: 6 role-specific dashboards with consistent modern UI, filter tabs, summary cards, and optimized queries.
- **User Management**: Complete modern redesign with metrics dashboard (6 summary cards), filter tabs (All/Active/Inactive/Locked/No MFA/Admin), real-time search, sortable tables, tabbed user profiles (Identity/Roles/Security/Activity), single-page create/edit forms with validation, security indicators, compliance alerts, and WCAG 2.1 AA accessibility features. Uses efficient single-page form pattern for experienced administrators.
- **Notification Management**: Modern UI redesign with 6 metric cards (Total/Unread/Read/Today/This Week/Low Stock), filter tabs with real-time JavaScript filtering, reusable Jinja2 macros (_macros.html) for notification cards and icons, dedicated CSS (notifications-ui.css) matching established design patterns, offcanvas bell dropdown with AJAX loading, clear all modal with confirmation, individual delete functionality with smooth animations, and WCAG 2.1 AA accessibility. Notification view precomputes metric counts server-side for performance.

### Database Architecture
- **Schema**: Based on the authoritative ODPEM `aidmgmt-3.sql` schema (40 tables).
- **Key Design Decisions**:
    - **Data Consistency**: All `varchar` fields in uppercase.
    - **Auditability**: `create_by_id`, `create_dtime`, `version_nbr` standard on all ODPEM tables. Audit fields now use `user.user_name` (varchar(20)) for consistent tracking across all system operations.
    - **Precision**: `DECIMAL(15,4)` for quantity fields.
    - **Status Management**: Integer/character codes for entity statuses, with lookup tables.
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col`.
    - **User Management**: Enhanced `public.user` table with `user_name` field (varchar(20), NOT NULL), MFA, lockout, password management, agency linkage, and `citext` for case-insensitive email.
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