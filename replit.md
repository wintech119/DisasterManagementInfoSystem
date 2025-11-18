# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM. It is designed to manage the full lifecycle of disaster relief supplies, from inventory tracking and donation management to relief request processing and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with RBAC. Its purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities including inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (2025-11-18)
- **Status Dropdown & Warehouse Count Fix (Batch Drawer)**: Fixed batch-allocation.js updateMainPageDisplay() to properly update status dropdown and warehouse count when LM edits allocations in batch drawer. Root cause: Code tried to set dropdown value BEFORE rebuilding options. Fix: Rebuilt dropdown with correct options (e.g., ['P', 'L'] for partial allocation) FIRST, then set value. Now when LM changes allocation 10→9, status auto-changes F→P, dropdown shows correct options, and warehouse count displays "1 warehouse" instead of "0 warehouse". Added status map data to approve.html template for JavaScript access.
- **Status Dropdown Auto-Reset Fix**: Fixed status dropdown not resetting from FILLED to PARTLY FILLED when LM reduces allocation below requested amount. Root cause: Code was trying to set dropdown value BEFORE updating options, so when status was 'F' with only ['F'] option and allocation dropped, it couldn't switch to 'P' because that option didn't exist yet. Fix: Swapped order in updateStatusDropdown() to call updateAllowedStatusOptions() FIRST (rebuilds dropdown with correct options ['P', 'L']), then set value. Now when allocation drops from 20/20 to 19/20, status correctly auto-resets from F→P, and LM can manually select 'L' (Allowed Limit) from dropdown.
- **Status Code Fix**: Fixed status auto-update logic in batch-allocation.js to use correct backend status codes ('R'=Requested, 'P'=Partly Filled, 'F'=Filled) instead of incorrect 'A' (Approved), matching item_status_service.py logic.
- **LM Notification Fix**: Fixed Logistics Managers not receiving notifications when Logistics Officers submit packages. Updated role code from 'LOGISTICS_MANAGER' to correct 'LM'.

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
The application utilizes a modular blueprint architecture with a database-first approach based on a pre-existing ODPEM `aidmgmt-3.sql` schema. Key architectural decisions include:
- **UI/UX Design**: Consistent modern UI with a comprehensive design system, shared Jinja2 components, GOJ branding, accessibility (WCAG 2.1 AA), and standardized workflow patterns. It features role-specific dashboards and comprehensive management modules for various entities (Event, Warehouse, User, etc.) with CRUD operations, validation, and optimistic locking.
- **Notification System**: Real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations.
- **Donation Processing**: Full workflow for donation management, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory. Automatic verification on acceptance is an MVP feature.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency (uppercase varchars), auditability, precision (`DECIMAL(15,4)`), and optimistic locking across all tables. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table.
- **Data Flow Patterns**: End-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities. Utilizes dedicated services like `ItemStatusService` and `InventoryReservationService`.
- **Role-Based Access Control (RBAC)**: Implemented via a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Specific CRUD operations are restricted by role (e.g., CUSTODIAN for item management).

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