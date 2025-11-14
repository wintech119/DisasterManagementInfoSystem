# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the full lifecycle of disaster relief supplies. It ensures compliance with government processes using the `aidmgmt-3.sql` schema. The system streamlines inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, supporting disaster event coordination and supply allocation. It includes user administration with RBAC, donor/agency/custodian management, inventory transfers, location tracking, analytics, reporting, and robust security features. The project aims to provide a centralized, efficient, and transparent system for disaster relief operations in Jamaica.

## User Preferences
- **Communication style**: Simple, everyday language.
- **UI/UX Requirements**:
  - All pages MUST have consistent look and feel with Relief Package preparation pages
  - Modern, polished design with summary cards, filter tabs, and clean layouts
  - Easy to use and user-friendly across all features
  - Consistent navigation patterns throughout the application

## Recent Changes

### November 14, 2025 - Phase 5: User Profile Pages Complete
**Major Feature:** Implemented comprehensive user profile system with role-specific sections

#### User Profile System
- **Profile Blueprint** (`app/features/profile.py`): 4 routes for complete profile management
  - `/profile/` - View profile with role-specific features display
  - `/profile/edit` - Edit personal information with validation
  - `/profile/change-password` - Secure password change with guidelines
  - `/profile/preferences` - Notification settings management

- **Modern UI Templates**: All profile pages match dashboard styling with:
  - Clean card-based layouts
  - Role-specific feature sections organized by category
  - Personal information and account status displays
  - Security actions and password guidelines
  - Notification preference toggles

- **FeatureRegistry Integration**: Profile displays user's accessible features organized by category
- **Security Features**: Current password verification, 8-character minimum, password strength validation
- **Account Details**: Shows user's primary role, assigned warehouses, agency affiliation

**Technical Implementation:**
- Clean blueprint architecture with no unnecessary dependencies
- Uses FeatureRegistry for role-based feature display
- Form validation with helpful user guidance
- Modern UI consistent with relief-requests-ui.css styling

**User Testing Note:** 
- Profile view fully functional (verified in logs)
- Edit and preferences routes need user testing to verify database schema compatibility
- Minor clarification needed on notification preferences persistence

### November 14, 2025 - Phase 3: Role-Based Dashboards Complete
**Major Feature:** Implemented comprehensive role-based dashboard system with modern UI

#### Dashboard System
- **6 Role-Specific Dashboards**: Created dedicated dashboards for Logistics, Agency, Director, Admin, Inventory, and General users
- **Modern UI Consistency**: All dashboards match Relief Package preparation UI with:
  - Summary metric cards (render_summary_cards macro)
  - Filter tabs with count badges
  - Modern table styling (relief-requests-table class)
  - Primary/secondary action buttons (btn-relief-primary, btn-relief-secondary)
  - Color-coded status badges
  - Empty state messages with icons
  - relief-requests-ui.css styling throughout

#### Dashboard Features by Role
1. **Logistics Dashboard** (`/dashboard/logistics`)
   - Fulfillment queue with filters: Pending/In Progress/Ready/Completed/All
   - Quick access to package preparation
   - Inventory metrics and low stock alerts

2. **Agency Dashboard** (`/dashboard/agency`)
   - Agency-specific relief requests
   - Filters: Active/Draft/Pending/Approved/Completed
   - Create new request button
   - Edit/view actions based on request status

3. **Director Dashboard** (`/dashboard/director`)
   - Eligibility review queue for ODPEM executives
   - Filters: Pending/Approved/In Progress/Completed/All
   - Quick access to eligibility review workflow

4. **Admin Dashboard** (`/dashboard/admin`)
   - System-wide metrics: Users/Agencies/Warehouses/Items
   - Recent activity feed
   - Quick links to all administrative features

5. **Inventory Dashboard** (`/dashboard/inventory`)
   - Inventory value and stock metrics
   - Low stock alerts with detailed table
   - Quick actions for inventory management

6. **General Dashboard** (`/dashboard/general`)
   - Fallback for users without specific dashboard
   - Welcome message with role display
   - Feature list based on user permissions

#### Technical Architecture
- **Smart Role Routing**: Main dashboard (`/`) automatically routes users to appropriate dashboard using `FeatureRegistry.get_primary_role()`
- **Priority-Based Role Detection**: Handles users with multiple roles by priority (SYSTEM_ADMINISTRATOR > Directors > Logistics > Inventory > Agency)
- **DashboardService Integration**: All dashboards use centralized service for widgets, metrics, and quick actions
- **Optimized Queries**: Uses SQLAlchemy joinedload for efficient related data fetching
- **Filter Support**: Each dashboard includes filter functionality with real-time count badges

#### Test Accounts for Dashboard Testing
Created dedicated test users with single roles (password: `test123`):
- **test.logistics@odpem.gov.jm** - Logistics Manager only
- **test.agency@gmail.com** - Agency Shelter only
- **test.director@odpem.gov.jm** - Director General only
- **test.inventory@odpem.gov.jm** - Inventory Clerk only

Existing admin: **admin@odpem.gov.jm** (password: `admin123`)

### Previous Updates

#### Feature Access Registry (Phases 1-2)
- **FeatureRegistry** (`app/core/feature_registry.py`): 26 features mapped to verified database role codes
- **DashboardService** (`app/services/dashboard_service.py`): Centralized service for dashboard data, widgets, metrics
- **Template Helpers**: Jinja2 functions for feature access checks (has_feature, get_feature_details, etc.)
- **Reusable Macros**: `_feature_card.html`, `_feature_nav_item.html` for consistent UI components

## System Architecture

### Technology Stack
- **Backend**: Python 3.11, Flask 3.0.3
- **Database ORM**: SQLAlchemy 2.0.32 with Flask-SQLAlchemy
- **Authentication**: Flask-Login 0.6.3 with Werkzeug
- **Frontend**: Server-side rendering with Jinja2, Bootstrap 5.3.3, Bootstrap Icons
- **Data Processing**: Pandas 2.2.2

### Application Structure
- **Modular Blueprint Architecture**: Feature-specific blueprints under `app/features/`.
- **Dashboard Blueprint**: Role-based routing with 6 dedicated dashboard views
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
    - **Auditability**: `create_by_id`, `create_dtime`, `version_nbr` standard on all ODPEM tables, plus workflow-specific audit columns.
    - **Precision**: `DECIMAL(15,4)` for quantity fields.
    - **Status Management**: Integer/character codes for entity statuses, with lookup tables for `reliefrqst_status` and `reliefrqstitem_status`.
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col` to prevent concurrent update conflicts.
    - **User Management**: Enhanced `public.user` table with MFA, lockout, password management, agency linkage, and `citext` for case-insensitive email.
    - **New Workflows**: `agency_account_request` and `agency_account_request_audit` tables for account creation workflows.

### Data Flow Patterns
- **AIDMGMT Relief Workflow**: End-to-end process from request creation (agencies) to eligibility review (ODPEM directors), package preparation (logistics), and distribution.
- **Dashboards**: Role-based dashboard routing with 6 specialized views (Logistics, Agency, Director, Admin, Inventory, General). Main dashboard (`/`) automatically routes users based on primary role.
- **Inventory Management**: Tracks stock by warehouse and item in the `inventory` table, including `usable_qty`, `reserved_qty`, `defective_qty`, `expired_qty`, with bin-level tracking.
- **Eligibility Approval Workflow**: Role-based access control (RBAC) and service layer for eligibility decisions.
- **Package Fulfillment Workflow**: Unified `packaging` blueprint with routes for pending fulfillment and package preparation. Includes features like summary metric cards, multi-warehouse allocation, dynamic item status validation, and a 4-step workflow sidebar.
- **Services**: `ItemStatusService` for status validation and `InventoryReservationService` for transaction-safe inventory reservation, preventing double-allocation.

### Role-Based Access Control (RBAC)
- **Feature Registry**: Centralized feature-to-role mapping in `app/core/feature_registry.py`
- **26 Features**: Mapped to 10 verified database role codes
- **Dashboard Service**: Provides role-specific widgets, metrics, and quick actions
- **Template Helpers**: Jinja2 functions for feature access checks (`has_feature`, `get_feature_details`, etc.)
- **Smart Routing**: Automatic dashboard routing based on user's primary role
- **Role Priority**: SYSTEM_ADMINISTRATOR > ODPEM_DG/DDG/DIR_PEOD > LOGISTICS_MANAGER > LOGISTICS_OFFICER > INVENTORY_CLERK > AGENCY_DISTRIBUTOR/SHELTER

### Verified Database Roles
- **SYSTEM_ADMINISTRATOR**: System Administrator - Full system access
- **LOGISTICS_MANAGER**: Logistics Manager - Oversees logistics operations
- **LOGISTICS_OFFICER**: Logistics Officer - Manages inventory and fulfillment
- **ODPEM_DG**: Director General - Chief executive of disaster operations
- **ODPEM_DDG**: Deputy Director General - Deputy head of disaster management
- **ODPEM_DIR_PEOD**: Director, PEOD - Plans and coordinates emergency operations
- **INVENTORY_CLERK**: Inventory Clerk - Stock management
- **AGENCY_DISTRIBUTOR**: Agency (Distributor) - Distributes relief items
- **AGENCY_SHELTER**: Agency (Shelter) - Manages shelter operations
- **AUDITOR**: Auditor - Compliance and audit access

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
