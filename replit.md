# DMIS - Disaster Management Information System

## Overview
DMIS (Disaster Management Information System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. Its core purpose is to provide a modern, efficient, and user-friendly solution for disaster preparedness and response. Key capabilities include inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, all while ensuring compliance with government processes and supporting disaster event coordination and supply allocation. The system emphasizes security, robust user administration with Role-Based Access Control (RBAC), inventory transfers, location tracking, analytics, and reporting.

## User Preferences
- **Communication style**: Simple, everyday language.
- **UI/UX Requirements**:
  - All pages MUST have consistent look and feel with Relief Package preparation pages
  - Modern, polished design with summary cards, filter tabs, and clean layouts
  - Easy to use and user-friendly across all features
  - Consistent navigation patterns throughout the application

## System Architecture
The application employs a modular blueprint architecture with a database-first approach, built upon a pre-existing ODPEM `aidmgmt-3.sql` schema.

### Technology Stack
- **Backend**: Python 3.11, Flask 3.0.3
- **Database ORM**: SQLAlchemy 2.0.32 with Flask-SQLAlchemy
- **Authentication**: Flask-Login 0.6.3 with Werkzeug
- **Frontend**: Server-side rendering with Jinja2, Bootstrap 5.3.3, Bootstrap Icons
- **Data Processing**: Pandas 2.2.2

### System Design
- **UI/UX Design**: Consistent modern UI, comprehensive design system, shared Jinja2 components, GOJ branding, accessibility (WCAG 2.1 AA), and standardized workflow patterns. Features role-specific dashboards and complete management modules with CRUD, validation, and optimistic locking.
- **Notification System**: Real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations. All notification POST actions (mark-read, clear-all, delete) use csrfFetch for CSRF protection.
- **Donation Processing**: Manages full workflow for donations, including intake, verification, batch-level tracking, expiry dates, and integration with warehouse inventory. Supports full donation workflow with country, currency, and cost breakdowns, including document uploads and robust validation.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Includes an enhanced `public.user` table, a new `itembatch` table (FEFO/FIFO), `itemcostdef` for cost types, `donation_doc` for document attachments, and composite primary keys.
- **Data Flow Patterns**: Supports end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing.
- **Role-Based Access Control (RBAC)**: Centralized feature registry, dynamic navigation, security decorators, smart routing, and a defined role hierarchy. Features secure user management with role assignment restrictions and both client-side and server-side validation. Role groups defined in `app/core/rbac.py`: `EXECUTIVE_ROLES` (DG, DDG, Dir PEOD), `LOGISTICS_ROLES`, `AGENCY_ROLES`. Use `is_executive()` or `@executive_required` decorator for eligibility approval access.
- **Security Features**: Strict nonce-based Content Security Policy (CSP), comprehensive Flask-WTF Cross-Site Request Forgery (CSRF) Protection, secure cookie configuration (Secure, HttpOnly, SameSite=Lax), Subresource Integrity (SRI) for CDN assets, global no-cache headers for sensitive pages, HTTP header sanitization, production-safe error handling, email obfuscation, query string protection for sensitive parameters, open redirect protection on login, and robust login authentication.
- **Timezone Standardization**: All datetime operations, database timestamps, audit trails, and user-facing displays use Jamaica Standard Time (UTC-05:00).
- **Key Features**: Universal visibility for approved relief requests, accurate inventory validation, batch-level reservation synchronization for draft packages, and automatic inventory table updates on dispatch. Relief package cancellation includes full reservation rollback using optimistic locking and transactional integrity. Implements robust relief request status management. Relief requests are restricted to GOODS items only - FUNDS items are excluded from item selection and blocked via server-side validation.
- **Relief Package Analytics Dashboard**: Executive-level analytics for dispatched relief packages (status 'D' and 'R'). Shows 4 KPI cards (Total Packages, Items Distributed, Delivery Locations, Requests Fulfilled), 4 interactive Chart.js charts (Destination Type pie, Parish bar, Timeline line, Top Destinations horizontal bar), and a detail table. Accessible to DG, Deputy DG, Director PEOD, and Logistics Manager roles.
- **Funds Donations Report**: Read-only report for ODPEM Executives (DG, Deputy DG, Director PEOD) showing all FUNDS-type donations. Displays Received Date, Origin Country, Donation Amount, Currency, and Location (Account #). Includes filters for Origin Country, Received Date range, and Currency. Features pagination (25 per page), sorted by received date (most recent first). Route: `/reports/funds_donations`.
- **Currency Conversion Service**: Cached exchange rate service for converting foreign currencies to JMD. Features:
  - `currency_rate` table for caching exchange rates (additive, no existing tables modified)
  - Service layer in `app/services/currency_service.py` with rate caching and conversion
  - External API integration currently disabled - system operates with manual/cached rates only
  - Rates can be inserted manually via `store_rate()` or `set_usd_jmd_rate()` methods
  - Display-only conversion - no stored values are modified
  - Graceful degradation if rates unavailable
  - Designed for easy integration with any future exchange rate API provider
- **Dynamic GOODS/FUNDS Donation Workflow**: Donation form dynamically adapts based on item category type (GOODS/FUNDS) via an API endpoint, automatically setting donation type and controlling field editability.
- **Donation Validation Rules**:
  - Total Donation Value is manually entered and validated against computed sum of line items (0.01 JMD tolerance). Mismatches are rejected with clear error messaging.
  - Document uploads require UPLOAD_FOLDER configuration; system fails with rollback if documents are uploaded without valid upload folder.
  - FUNDS items enforce quantity = 1.00 on both client-side and server-side.
- **Donation Intake Two-Stage Workflow**: 
  - **Workflow A (Entry)**: LOGISTICS_OFFICER creates/edits intakes. Selects verified donations (status='V'), filters only GOODS items. Creates dnintake with status 'I' (draft) or 'C' (submitted for verification). NO inventory/batch updates at this stage.
  - **Workflow B (Verification)**: LOGISTICS_MANAGER reviews submitted intakes (status='C'). Can adjust defective/expired quantities, batch details. Upon verification, status changes to 'V', ItemBatch records are created/updated, Inventory totals are updated, and Donation status changes to 'P' (Processed). All operations in a single atomic transaction with optimistic locking.
- **Relief Package Dispatch Workflow (Workflow C)**: LM Submit for Dispatch - Final dispatch operation when Logistics Manager submits a package:
  - **Service Layer**: `app/services/dispatch_service.py` implements the core algorithm:
    1. Undo LO reservations (from reliefpkg_item) in itembatch.reserved_qty and inventory.reserved_qty
    2. Overwrite reliefpkg_item with LM's final allocation plan
    3. Deplete usable stock in itembatch.usable_qty and inventory.usable_qty based on LM plan
    4. Update reliefpkg header status to 'D' (Dispatched) with dispatch_dtime
    5. Update reliefrqst_item.issue_qty with actual dispatched quantities
  - **Route**: POST `/packaging/package/<reliefpkg_id>/submit-dispatch` - LM-only access
  - **Data Integrity**: All operations execute in ONE atomic transaction with optimistic locking (version_nbr checks)
  - **Error Handling**: On any failure (version conflict, insufficient stock, missing records), entire transaction rolls back with user-friendly error message
  - **Isolation**: Does NOT modify Workflow A (LO packaging) or Workflow B (LM review) - only handles final dispatch step

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
- Flask-WTF
- requests

### Frontend CDN Resources
- Bootstrap 5.3.3 CSS/JS
- Bootstrap Icons 1.11.3
- Flatpickr