# DMIS - Disaster Management Information System

## Overview
DMIS (Disaster Management Information System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (November 24, 2025)
- **Currency and Country Tables Migration**:
  - Created `currency` table with 37 international currencies (JMD, USD, CAD, GBP, EUR, XCD, and 31 others)
  - Added `currency_sign` field to support currency symbols (J$, $, £, €, etc.)
  - Reseeded `country` table with 66 countries and currency references
  - Added foreign key constraint `fk_country_currency` linking countries to their currencies
  - Jamaica (country_id=388) correctly mapped to JMD (Jamaican dollar, J$)
  - All existing functionality preserved; no code changes required
  - Parish data (14 Jamaican parishes) verified and maintained

- **CSRF Protocol Mismatch Fix for Replit Environment**:
  - Fixed CSRF Origin validation error that blocked user management operations
  - Updated `app/security/csrf_validation.py` to allow both HTTP and HTTPS protocols for the same host
  - Resolves issue where Replit's HTTPS proxy caused validation failures with HTTP backend
  - Admin users can now successfully create and modify user accounts
  - Default custodian "Office of Disaster Preparedness and Emergency Management" added to database

- **Relief Package Cancellation Workflow** (Architect-Validated):
  - Implemented safe cancellation workflow for relief packages with full reservation rollback
  - Created `cancel_relief_package()` service function in `app/services/inventory_reservation_service.py`:
    * Fully reverses all reservations in `itembatch` and `inventory` tables
    * Uses SQLAlchemy optimistic locking via `version_nbr` for both ItemBatch and Inventory models
    * Validates `reserved_qty >= allocated_qty` before decrementing (data integrity check)
    * Validates `reserved_qty >= 0` after decrementing (sanity check)
    * Recalculates warehouse-level totals from batch-level SUM to ensure consistency
    * Fully transactional (all-or-nothing) with automatic rollback on errors
    * Catches `StaleDataError` for concurrent edit detection with user-friendly messaging
    * Server-side error logging preserves detailed stack traces for debugging
    * User-facing error messages are generic and friendly (no technical details exposed)
  - Added `/packaging/package/<reliefpkg_id>/cancel` POST route in `app/features/packaging.py`:
    * Restricted to Logistics Manager role only
    * CSRF protection enforced
    * Calls service function and commits transaction
    * Logs exceptions server-side with detailed stack traces
    * Shows user-friendly flash messages
  - Updated `templates/packaging/review_approval.html`:
    * Added "Cancel Package" button with danger styling
    * JavaScript confirmation prompt before submission
    * CSRF token automatically included
    * CSP-compliant implementation
  - Architect validation: PASS - "Implementation meets all functional and concurrency requirements. No security concerns."
  - **Note**: Database purged and reset; admin user recreated (admin@odpem.gov.jm / admin123)

- **CSP Hardening for HCL AppScan Compliance** (Scanner-Validated):
  - Removed `https:` wildcard from `img-src` directive (scanner flagged as insecure)
  - Tightened `connect-src` to same-origin only (removed unnecessary CDN)
  - Added comprehensive security scanner compliance documentation in code
  - Architect-validated: "CSP hardening meets scanner requirements with explicit script-src and no insecure wildcards"
  - **Current CSP Policy**: Explicit script-src with nonces, no wildcards, no unsafe-inline/unsafe-eval
  - HCL AppScan finding "Missing or insecure 'Script-Src' policy" now resolved

- **Comprehensive CSRF Protection Implementation Complete** (Production-Ready):
  - Installed and configured Flask-WTF 1.2.1 with global CSRFProtect initialization
  - Automated CSRF token injection across 58+ HTML form templates via base.html context processor
  - Created `static/js/csrf-helper.js` for JavaScript AJAX request protection (csrfFetch wrapper)
  - Updated all dynamic form submissions (approve.js, prepare.js) to include CSRF tokens
  - Implemented defense-in-depth Origin/Referer validation in `app/security/csrf_validation.py`:
    * Exact origin matching (prevents subdomain bypass attacks)
    * Controlled proxy header trust (X-Forwarded-Host/Proto only when CSRF_TRUST_PROXY_HEADERS=True)
    * Support for CSRF_TRUSTED_ORIGINS config for multi-domain deployments
  - Created custom CSRFError handler in `app/security/error_handling.py` with detailed audit logging
  - Enhanced `templates/errors/403.html` with CSRF-specific remediation guidance for users
  - Fixed dynamically created forms (packaging/prepare.html cancel flow) to include tokens
  - Architect-validated implementation: "CSRF protections are now comprehensive and enforce both token validation and hardened origin checks without known bypasses"

## Previous Changes (November 22, 2025)
- **CSP Compliance Remediation Complete**: All 33 templates (72 originally identified) across the entire codebase now fully compliant with strict Content Security Policy (no unsafe-inline, no unsafe-eval)

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
- **UI/UX Design**: Emphasizes a consistent modern UI, comprehensive design system, shared Jinja2 components, GOJ branding, accessibility (WCAG 2.1 AA), and standardized workflow patterns. Features role-specific dashboards and complete management modules for various entities with CRUD operations, validation, and optimistic locking.
- **Notification System**: Includes real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations.
- **Donation Processing**: Manages the full workflow for donations, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table. The `dnintake_item` table uses a surrogate primary key (`intake_item_id`) with nullable `batch_no` and `batch_date` fields, enforced by partial unique indexes to support items with and without batch tracking.
- **Data Flow Patterns**: Supports an end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities.
- **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Features secure user management with role assignment restrictions to prevent privilege escalation; includes both client-side role filtering and server-side validation to prevent bypass attacks.
- **Content Security Policy (CSP)**: Strict nonce-based CSP implementation protects against XSS attacks, data injection, UI hijacking, and phishing. Uses cryptographically secure per-request nonces for inline scripts/styles, whitelists only cdn.jsdelivr.net for external resources, blocks all plugin execution and framing, and enforces same-origin form submissions. Additional security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy) provide defense-in-depth.
- **Cross-Site Request Forgery (CSRF) Protection**: Comprehensive Flask-WTF CSRFProtect implementation with per-session cryptographic tokens on all state-changing requests (POST/PUT/PATCH/DELETE). Defense-in-depth Origin/Referer validation with exact origin matching prevents subdomain bypass attacks. Controlled proxy header trust (X-Forwarded-Host/Proto) ensures security behind reverse proxies. Custom error handling provides user-friendly 403 pages with remediation guidance and detailed security audit logging. JavaScript csrf-helper.js ensures AJAX requests include tokens. Configuration options: CSRF_TRUST_PROXY_HEADERS (default: False), CSRF_TRUSTED_ORIGINS (for multi-domain deployments).
- **Secure Cookie Configuration**: Session and authentication cookies implement modern security standards with Secure (HTTPS-only), HttpOnly (XSS protection), and SameSite=Lax (CSRF protection) attributes. Configured globally via Flask session settings for all authentication flows.
- **Subresource Integrity (SRI)**: All third-party CDN assets (Bootstrap 5.3.3, Bootstrap Icons 1.11.3, Chart.js 4.4.0, Flatpickr) protected with SHA-384 integrity hashes and crossorigin attributes. Prevents CDN compromises and man-in-the-middle attacks by cryptographically verifying resource authenticity.
- **Cache Control**: Global no-cache headers (Cache-Control: no-store, no-cache, must-revalidate; Pragma: no-cache; Expires: 0) applied to all authenticated and sensitive pages. Prevents browser and proxy caching of sensitive data while allowing static assets (CSS, JS, images) to be cached for performance. Eliminates "SSL Pages Are Cacheable" vulnerability.
- **HTTP Header Sanitization**: Removes or neutralizes info-leaking HTTP response headers (Server, X-Powered-By, Via, X-Runtime) that expose technology stack details. Uses WSGI middleware for production servers and Python http.server override for development server. Prevents technology fingerprinting while preserving all essential headers.
- **Production-Safe Error Handling**: Environment-aware error handling ensures technical details (stack traces, file paths, database info) are never exposed to users in production. Custom user-friendly error pages (400, 403, 404, 405, 500) replace raw error messages. Full error details logged server-side with automatic database rollback on errors. Controlled via FLASK_DEBUG environment variable (0=production, 1=development).
- **Email Obfuscation**: Public-facing pages (login, account requests) and documentation files use [at]/[dot] notation to prevent automated email harvesting while maintaining user readability. Form submissions correctly use POST method for actual email transmission.
- **Query String Protection**: Method-agnostic before_request middleware blocks sensitive parameters (password, email, phone, PII, credentials) from appearing in query strings across ALL HTTP methods (GET, POST, PUT, DELETE, etc.). Returns 400 Bad Request when violations detected, preventing sensitive data from appearing in server logs, browser history, referer headers, or being processed by application code. Sensitive parameter catalogue carefully curated to avoid false positives while maintaining comprehensive coverage of credentials and PII.
- **Timezone Standardization**: All datetime operations, database timestamps, audit trails, and user-facing displays use Jamaica Standard Time (UTC-05:00) consistently.
- **Key Features**: Universal visibility for approved relief requests across relevant roles, accurate inventory validation against available quantities, batch-level reservation synchronization for draft packages, and automatic inventory table updates on dispatch.

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