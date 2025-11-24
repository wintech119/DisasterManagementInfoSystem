# DMIS - Disaster Management Information System

## Overview
DMIS (Disaster Management Information System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. Its core purpose is to provide a modern, efficient, and user-friendly solution for disaster preparedness and response. Key capabilities include inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, all while ensuring compliance with government processes and supporting disaster event coordination and supply allocation. The system emphasizes security, robust user administration with Role-Based Access Control (RBAC), inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (November 24, 2025)

### Database Purge - All Data Cleared
- Safely purged all data from 48 database tables using TRUNCATE CASCADE
- Reset all 25 sequences to start from 1
- Complete database schema preserved:
  - All 48 tables intact with structure
  - All 109 foreign key constraints preserved
  - All indexes, columns, and constraints maintained
- Application verified working after purge:
  - All workflows running correctly
  - All security features intact (CSP, CSRF, cookies, headers)
  - No schema changes or regressions
  - Ready for fresh data entry

### Login Page - Agency Registration Hidden
- Removed Agency Registration section from login page
- Login page now only shows standard login form (email + password)
- All other elements remain intact (logos, styling, footer, security)
- No backend changes - registration route still exists but is not accessible from login page

### Donation Item Duplicate Error Handling
- Improved error handling when users attempt to add the same item twice to a donation
- Catches `UniqueViolation` (pk_donation_item) at the application level instead of exposing raw SQL errors
- Shows friendly message: "This item has already been added to the donation. Please edit the existing item instead."
- Maintains all form values so users don't lose their input during validation errors
- Highlights the duplicate item field with Bootstrap validation styling (red border + inline message)
- No database schema changes - composite primary key (donation_id, item_id) remains unchanged
- All existing security and workflow features preserved (CSP, CSRF, cookies, etc.)

### Login Authentication Fix
- Fixed issue where users could not log back in after logout
- Added proper validation checks in login route to verify user is active and not locked
- Enhanced `load_user` function to validate user status before session restoration
- Login now checks: password correctness, `is_active` flag, `status_code == 'A'`, and `is_locked` property
- Provides specific error messages for inactive accounts vs. locked accounts
- All existing security features maintained (CSRF, CSP, secure cookies, etc.)

### Donation Table Schema Update
- Made `origin_country_id` column nullable in the `donation` table
- Allows donations without a specified origin country

### Fixed Intermittent "Disappearing Records" Issue
- Fixed bug where master records (User, Warehouse) appeared briefly after creation and then disappeared from list views
- Root cause: URL filter parameters persisting in browser navigation history
- Solution: All create/edit operations now redirect to list views with explicit `?filter=all` parameter
- Updated warehouse create/edit redirects to always show "All" view
- Updated navigation links to include `?filter=all` parameter

### CSRF Origin Validation Fix
- Fixed CSRF validation to work correctly in Replit proxy environment
- Allows both HTTP and HTTPS protocols for same host while maintaining hostname validation security
- Replit proxy uses HTTPS while Flask dev server uses HTTP

### Database Migration
- Created currency table with 37 currencies
- Updated country table (66 countries) with foreign key to currency
- Verified parish table (14 parishes)
- Enabled citext extension for PostgreSQL
- Added default custodian "Office of Disaster Preparedness and Emergency Management" (ID=3)

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
- **Notification System**: Real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations.
- **Donation Processing**: Manages full workflow for donations, including intake, verification, batch-level tracking, expiry dates, and integration with warehouse inventory.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Includes an enhanced `public.user` table, a new `itembatch` table (FEFO/FIFO), and composite primary keys.
- **Data Flow Patterns**: Supports end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing.
- **Role-Based Access Control (RBAC)**: Centralized feature registry, dynamic navigation, security decorators, smart routing, and a defined role hierarchy. Features secure user management with role assignment restrictions and both client-side and server-side validation.
- **Content Security Policy (CSP)**: Strict nonce-based CSP protects against XSS, data injection, UI hijacking, and phishing. Uses cryptographically secure per-request nonces for inline scripts/styles, whitelists only cdn.jsdelivr.net, blocks plugin execution/framing, and enforces same-origin form submissions. Includes additional security headers.
- **Cross-Site Request Forgery (CSRF) Protection**: Comprehensive Flask-WTF CSRFProtect with per-session cryptographic tokens on all state-changing requests. Defense-in-depth Origin/Referer validation, controlled proxy header trust, custom error handling, and JavaScript helper for AJAX requests.
- **Secure Cookie Configuration**: Session and authentication cookies implement modern security standards with Secure, HttpOnly, and SameSite=Lax attributes.
- **Subresource Integrity (SRI)**: All third-party CDN assets are protected with SHA-384 integrity hashes and crossorigin attributes to prevent compromises.
- **Cache Control**: Global no-cache headers applied to all authenticated and sensitive pages to prevent caching of sensitive data, while allowing static assets to be cached.
- **HTTP Header Sanitization**: Removes or neutralizes info-leaking HTTP response headers (Server, X-Powered-By, Via, X-Runtime).
- **Production-Safe Error Handling**: Environment-aware error handling ensures technical details are never exposed to users in production. Custom user-friendly error pages and server-side logging with automatic database rollback.
- **Email Obfuscation**: Public-facing pages use [at]/[dot] notation to prevent automated email harvesting.
- **Query String Protection**: Method-agnostic middleware blocks sensitive parameters (password, email, phone, PII, credentials) from appearing in query strings across all HTTP methods.
- **Timezone Standardization**: All datetime operations, database timestamps, audit trails, and user-facing displays use Jamaica Standard Time (UTC-05:00).
- **Key Features**: Universal visibility for approved relief requests, accurate inventory validation, batch-level reservation synchronization for draft packages, and automatic inventory table updates on dispatch. Relief package cancellation includes full reservation rollback using optimistic locking and transactional integrity.

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

### Frontend CDN Resources
- Bootstrap 5.3.3 CSS/JS
- Bootstrap Icons 1.11.3
- Flatpickr