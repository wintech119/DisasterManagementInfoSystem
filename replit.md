# DMIS - Disaster Management Information System

## Overview
DMIS (Disaster Management Information System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (November 24, 2025)
- **Master Records Disappearing Fix**:
  - Fixed intermittent issue where newly created warehouses/users appeared briefly then disappeared from list views
  - **Warehouse Fix**: After creation, now redirects to list with `filter='all'` instead of detail view, ensuring new records are immediately visible regardless of previous filter state
  - **User List Fix**: Added pageshow event listener to reset client-side filters when page is restored from browser back/forward cache
  - Root cause: Browser back button preserved previous filter URLs (warehouses) or cached JavaScript state (users), causing new records to be filtered out
  - Zero security regression: All CSP, CSRF, cache-control protections maintained
  - Architect reviewed: No regressions, all security controls intact

- **Duplicate Donation Items Fix**:
  - Fixed bug where same item could be added multiple times to a single donation
  - Added server-side validation to detect and prevent duplicate item_ids in donation form submissions
  - Displays user-friendly error message showing item name when duplicates are detected
  - Prevents database IntegrityError on donation_item table's composite primary key (donation_id, item_id)
  - Zero regression; all existing donation functionality preserved

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
- **Donation Processing**: Manages the full workflow for donations, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory. Includes features for preventing duplicate donation items, and tracking donation origin and value.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table. Includes tables for currency and country data.
- **Relief Package Cancellation Workflow**: Implemented safe cancellation workflow for relief packages with full reservation rollback, using optimistic locking and transactional integrity.
- **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Features secure user management with role assignment restrictions and both client-side and server-side validation.
- **Content Security Policy (CSP)**: Strict nonce-based CSP implementation protects against XSS attacks, data injection, UI hijacking, and phishing. Uses cryptographically secure per-request nonces and whitelists only necessary external resources.
- **Cross-Site Request Forgery (CSRF) Protection**: Comprehensive Flask-WTF CSRFProtect implementation with per-session cryptographic tokens on all state-changing requests. Includes defense-in-depth Origin/Referer validation and custom error handling.
- **Secure Cookie Configuration**: Session and authentication cookies implement modern security standards with Secure, HttpOnly, and SameSite=Lax attributes.
- **Subresource Integrity (SRI)**: All third-party CDN assets are protected with SHA-384 integrity hashes and crossorigin attributes.
- **Cache Control**: Global no-cache headers applied to all authenticated and sensitive pages to prevent caching of sensitive data.
- **HTTP Header Sanitization**: Removes or neutralizes info-leaking HTTP response headers.
- **Production-Safe Error Handling**: Environment-aware error handling ensures technical details are not exposed to users in production, providing custom user-friendly error pages and server-side logging.
- **Query String Protection**: Middleware blocks sensitive parameters from appearing in query strings across all HTTP methods.
- **Timezone Standardization**: All datetime operations and displays consistently use Jamaica Standard Time (UTC-05:00).
- **Key Features**: Universal visibility for approved relief requests, accurate inventory validation, batch-level reservation synchronization for draft packages, and automatic inventory table updates on dispatch.

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