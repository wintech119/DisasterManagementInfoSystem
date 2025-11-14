# DRIMS - Disaster Relief Inventory Management System

## Overview

DRIMS (Disaster Relief Inventory Management System) is a comprehensive web-based platform for the Government of Jamaica's ODPEM, designed to manage the full lifecycle of disaster relief supplies. It ensures compliance with established government processes by utilizing the authoritative ODPEM `aidmgmt-3.sql` schema.

The system's core purpose is to streamline inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, supporting disaster event coordination and supply allocation. It offers a robust management suite including user administration with RBAC, donor/agency/custodian management, inventory transfers, and location tracking. Key capabilities also include analytics, reporting, donation management with audit trails, and strong security features like role-based access control and audit logging. The project aims to provide a centralized, efficient, and transparent system for disaster relief operations in Jamaica.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Technology Stack
- **Backend**: Python 3.11 + Flask 3.0.3
- **Database ORM**: SQLAlchemy 2.0.32 with Flask-SQLAlchemy
- **Authentication**: Flask-Login 0.6.3 with Werkzeug
- **Frontend**: Server-side rendering with Jinja2, Bootstrap 5.3.3, Bootstrap Icons
- **Data Processing**: Pandas 2.2.2

### Application Structure
- **Modular Blueprint Architecture**: `app.py` for main application, with feature-specific blueprints organized under `app/features/`.
- **Database-First Approach**: SQLAlchemy models (`app/db/models.py`) map to a pre-existing ODPEM `aidmgmt-3.sql` schema.
- **Shared Utilities**: Located in `app/core/`.
- **Templates**: Jinja2 templates (`templates/`) enforce consistent Government of Jamaica (GOJ) branding.

### UI/UX Design
- **Consistent Styling**: Global CSS utilities (`.drims-card`, `.drims-table`) ensure uniform appearance with rounded corners and subtle shadows.
- **Navigation**: `table-clickable` class provides row-click navigation.
- **Button Styling**: Standardized `btn-sm` for actions (view, edit, delete).
- **Responsive Design**: Fixed header, collapsible sidebar, dynamic content margins, and touch-friendly interactions.
- **Branding**: Utilizes GOJ branding with primary green (`#009639`) and gold accent (`#FDB913`), including official logos on login, navigation, and footer with accessibility features.
- **User Experience**: Icon-based empty states and professional eligibility review interfaces.
- **Needs Lists Design Pattern**: Unified modern UI across Relief Requests and Eligibility workflows:
  - **Summary Metric Cards**: 3-card dashboard showing key metrics (total, high priority, items)
  - **Filter Tabs**: Functional tabs with live count badges for filtering by priority
  - **Workflow Sidebar**: 5-step visual progress indicator with clean modern design:
    - White card background with blue header bar (#007bff)
    - Green checkmarks (#28a745) for completed steps with vertical connecting lines
    - Blue active step indicator, white circles with green borders for pending steps
    - Sticky positioning (`position: sticky; top: 1.25rem`) - sidebar doesn't move when scrolling on desktop
    - Optional completion message box at bottom for workflow status updates
    - Backward compatible macro supporting both global completion flag and step-by-step completion
  - **Status Badges**: Color-coded badges for status and priority levels
  - **Standardized Tables**: `relief-requests-table` class with consistent styling, row hover states
  - **Action Buttons**: `btn-relief-primary` and `btn-relief-secondary` for consistent CTA styling
  - **Shared Components**: Jinja2 macros (`_status_badge.html`, `_summary_cards.html`, `_workflow_sidebar.html`)
  - **Shared Stylesheet**: `relief-requests-ui.css` for unified styling across both workflows
- **Agency Relief Request Workflow (5 Steps)**:
  1. **Create Request** - Provide basic request details and disaster event (status=0)
  2. **Add Items** - Add items with quantities, urgency levels, and justifications (status=0)
  3. **Review & Submit** - Submit request to ODPEM for processing (status=0→1)
  4. **Eligibility Review** - ODPEM reviews and approves/denies (status=1→3/4/8)
  5. **Fulfillment & Delivery** - ODPEM logistics prepares and delivers items (status=3→5→6/7)

### Database Architecture
- **Schema**: Based on the authoritative ODPEM `aidmgmt-3.sql` schema, comprising 40 tables.
- **Key Design Decisions**:
    - **Data Consistency**: All `varchar` fields are stored in uppercase.
    - **Auditability**: `create_by_id`, `create_dtime`, and `version_nbr` are standard on all ODPEM tables. Many tables also include workflow-specific audit columns (e.g., `review_by_id`, `review_dtime`, `action_by_id`, `action_dtime` for relief requests).
    - **Precision**: `DECIMAL(15,4)` for all quantity fields.
    - **Status Management**: Integer/character codes for entity statuses.
    - **Composite Keys**: Utilized in many tables for unique identification.
    - **Referential Integrity**: Enforced via foreign keys and complex `CHECK` constraints (e.g., `c_agency_5` for agency types, `c_reliefrqst_3` for status_reason_desc requirement).
    - **Optimistic Locking**: Implemented across all 40 tables using SQLAlchemy's `version_id_col` to prevent concurrent update conflicts, raising `OptimisticLockError`.
    - **Standardized Status Management**: Migration to `reliefrqst_status` lookup table for standardized request statuses with `reason_rqrd_flag` indicating which statuses require justification.
    - **Relief Request Item Status**: New `reliefrqstitem_status` lookup table with 7 status codes (R, U, W, D, P, L, F) and `item_qty_rule` for quantity validation.
    - **User Account Management**: Enhanced `public.user` table with fields for MFA, account lockout, password management, agency linkage, and account status, and `citext` extension for case-insensitive email.
    - **New Workflows**: Introduced `agency_account_request` and `agency_account_request_audit` tables for managing agency account creation workflows without altering existing schema.

### Data Flow Patterns
- **AIDMGMT Relief Workflow**: Complete end-to-end workflow covering:
  1. **Relief Request Creation** (agencies) - Create and edit drafts via `/relief-requests/create`, Status: DRAFT (0) → AWAITING_APPROVAL (1)
  2. **Eligibility Review** (ODPEM directors) - Status: AWAITING_APPROVAL (1) → SUBMITTED (3) or INELIGIBLE (8)
  3. **Package Preparation** (logistics officers/managers) - Status: SUBMITTED (3) → PART_FILLED (5) → FILLED (7)
  4. **Distribution & Intake** (agencies receive goods)
- **Agency User Interface**: Simplified view showing only Edit (drafts) and View (all other statuses) actions. No access to eligibility review or fulfillment actions.
- **ODPEM Director Dashboard**: Unified view at `/director/dashboard` for DG/DDG/Dir/PEOD roles showing all relief requests with 5 filter tabs:
  - **Pending Review**: Requests awaiting eligibility review (STATUS_AWAITING_APPROVAL)
  - **Pending Fulfillment**: Approved requests being fulfilled by logistics (STATUS_SUBMITTED, STATUS_PART_FILLED)
  - **In Progress**: All active requests (STATUS_AWAITING_APPROVAL, STATUS_SUBMITTED, STATUS_PART_FILLED)
  - **Completed**: Fully fulfilled requests (STATUS_FILLED)
  - **All**: Complete historical view of all requests
  - Dashboard includes summary metric cards, status badges, and role-appropriate action buttons (Review Eligibility for pending, View for others)
- **Inventory Management**: Tracks stock by warehouse and item in the `inventory` table, including `usable_qty`, `reserved_qty`, `defective_qty`, `expired_qty`, with bin-level tracking via the `location` table.
- **Eligibility Approval Workflow**: Integrated role-based access control (RBAC) with `has_permission` and `@permission_required` decorators. Service layer for eligibility decisions, notifications, and workflow enforcement. ODPEM directors access via `/eligibility/pending`.
- **Package Fulfillment Workflow** (Modern UI): 
  - **Primary Routes**: `/packaging/pending-fulfillment` (list), `/packaging/<id>/prepare` (modern preparation interface)
  - **Friendly Alias**: `/relief-requests/<id>/prepare-package` redirects to packaging workflow
  - **Legacy Routes**: `/packages/*` blueprint deprecated, redirects to modern `/packaging/*` endpoints
  - **Modern UI Features**:
    - 4 Summary metric cards (Total Items, Fully Allocated, Partial, Unallocated) with live updates
    - Search and filter bar with "Jump to First Unallocated" functionality
    - Multi-warehouse allocation: Shows all warehouses with stock for each item
    - Real-time calculations: Allocated totals, remaining quantities, and status badges update automatically
    - Inline inventory validation: Prevents over-allocation beyond available stock
    - **Dynamic Item Status Validation**: Comprehensive status dropdown with intelligent validation:
      - 7 status codes (R=Requested, U=Unavailable, W=Awaiting, D=Denied, P=Partial, L=Allowed Limit, F=Filled)
      - Automatic status updates based on allocation (0→R, partial→P, full→F)
      - Manual status changes with dynamic dropdown options (P→{P,L}, F locked, zero→{D,U,W})
      - Client-side validation with real-time error feedback
      - Server-side validation enforces quantity limits and status transition rules
      - Status preservation prevents discarding legitimate manual statuses during recalculation
    - 4-step workflow sidebar: Submitted → Prepare → Approval → Execute/Dispatch
    - Lock management: Prevents concurrent editing with lock acquisition/release
    - Role-based actions: Save Draft (all), Submit for Approval (LO), Send for Dispatch (LM), Cancel
  - **Data Persistence**: Allocations saved to `ReliefPkg` and `ReliefPkgItem` tables, pre-populated on page load
  - **Item Status Service** (`app/services/item_status_service.py`): Centralized service for status validation:
    - `load_status_map()`: Cached lookup of active status codes with force reload support
    - `compute_allowed_statuses()`: Computes allowed status transitions based on allocation state
    - `validate_status_transition()`: Validates manual status changes against business rules
    - `validate_quantity_limit()`: Validates allocated quantities against request limits
  - **Inventory Reservation Service** (`app/services/inventory_reservation_service.py`): Transaction-safe inventory reservation system:
    - `reserve_inventory()`: Updates inventory.reserved_qty based on allocation deltas with row-level locking
    - `release_all_reservations()`: Releases reservations when package preparation is canceled or abandoned
    - `commit_inventory()`: Converts reservations to actual deductions on dispatch (decreases usable_qty and reserved_qty)
    - **Integrated with lock lifecycle**: Reservations automatically released when locks expire via `fulfillment_lock_service`
    - **Prevents double-allocation**: Concurrent package preparation blocked by reserved quantities
    - **Transaction coupling**: All allocation updates, reservations, and commits occur in single database transactions

## External Dependencies

### Required Database
- **PostgreSQL 16+** (production) with `citext` extension.
- **SQLite3** (development fallback).

### Python Packages
- Flask 3.0.3
- Flask-SQLAlchemy 3.1.1
- Flask-Login 0.6.3
- SQLAlchemy 2.0.32
- psycopg2-binary 2.9.9
- Werkzeug 3.0.3
- pandas 2.2.2
- python-dotenv 1.0.1

### Frontend CDN Resources
- Bootstrap 5.3.3 CSS/JS
- Bootstrap Icons 1.11.3

### Database Schema and Initialization
- **DRIMS_Complete_Schema.sql**: Used for initial database setup and seeding reference data.
- `scripts/init_db.py`: Executes the complete schema.
- `scripts/seed_demo.py`: Populates minimal test data.