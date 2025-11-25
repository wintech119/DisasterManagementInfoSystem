# DMIS - Disaster Management Information System

## Overview
DMIS (Disaster Management Information System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. Its core purpose is to provide a modern, efficient, and user-friendly solution for disaster preparedness and response. Key capabilities include inventory tracking, donation management, relief request processing, and distribution across multiple warehouses, all while ensuring compliance with government processes and supporting disaster event coordination and supply allocation. The system emphasizes security, robust user administration with Role-Based Access Control (RBAC), inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (November 24, 2025)

### Donation Item Table Rebuild (Migration 014)
- **Table Rebuilt**: Dropped and recreated donation_item table to match exact target DDL structure
- **FK Handling**: Safely dropped/recreated FK from dnintake_item during rebuild
- **Column Order Aligned**: Columns now match target DDL order for audit traceability
- **All Constraints Preserved**: c_donation_item_0, 1a, 1b, 1c, 2, 10
- **addon_cost Retained**: Required by c_donation_item_10 constraint (item_cost + addon_cost > 0.00)
- **Referential Integrity**: All FKs intact (donation, item, unitofmeasure) + dnintake_item FK restored
- **Migration File**: `migrations/014_recreate_donation_item_table.sql`

### Donation Intake Item Table Migration (Migration 013)
- **Primary Key Restructured**: Changed from serial `intake_item_id` to composite PK `(donation_id, inventory_id, item_id, batch_no)`
- **New Column Added**: `ext_item_cost` DECIMAL(12,2) for extended cost tracking (total qty * avg_unit_value)
- **Batch Tracking Enforced**: `batch_no`, `batch_date`, `expiry_date` now required (NOT NULL)
- **Constraint Updates**: 
  - `c_dnintake_item_1c`: Changed from `expiry_date >= CURRENT_DATE` to `expiry_date >= batch_date`
  - `c_dnintake_item_1e`: New constraint for `ext_item_cost >= 0.00`
- **Performance Indexes**: Created `dk_dnintake_item_1` and `dk_dnintake_item_2` for efficient queries
- **Code Updates**: Updated SQLAlchemy DonationIntakeItem model with composite PK and new columns
- **Zero Breaking Changes**: Table was empty during migration; referential integrity preserved
- **Migration File**: `migrations/013_migrate_dnintake_item_table_to_target_ddl.sql`

### Donation Item Table Migration (Migration 012)
- **Quantity Precision**: Changed `item_qty` from DECIMAL(12,2) to DECIMAL(9,2) with default 1.00
- **Audit Trail Enforcement**: Made `verify_by_id` and `verify_dtime` NOT NULL (previously nullable)
- **Auto-Timestamps**: Made `update_dtime` NOT NULL with default CURRENT_TIMESTAMP
- **Cost Validation**: Added constraint `c_donation_item_10` ensuring `item_cost + addon_cost > 0.00`
- **Code Updates**: Updated SQLAlchemy DonationItem model to match new schema
- **Zero Breaking Changes**: All application code continues working without modifications
- **Referential Integrity Preserved**: All foreign keys intact (donation, item, unitofmeasure); downstream table dnintake_item functional
- **Migration File**: `migrations/migrate_donation_item_table_to_target_ddl.sql`

### Donation Table Cost Breakdown Migration (Migration 011)
- **Cost Breakdown Fields Added**: Enhanced donation tracking with detailed cost breakdown
  - `tot_item_cost` (renamed from `tot_donated_value`): Total value of donated items (DECIMAL(12,2), > 0.00)
  - `storage_cost`: Warehousing/storage costs (DECIMAL(12,2), > 0.00, default 0.01)
  - `haulage_cost`: Transportation/shipping costs (DECIMAL(12,2), > 0.00, default 0.01)
  - `other_cost`: Miscellaneous costs (DECIMAL(12,2), > 0.00, default 0.01)
  - `other_cost_desc`: Description of other costs (VARCHAR(255), nullable)
- **Origin Country Required**: `origin_country_id` changed from nullable to NOT NULL
- **Enhanced Validation**: Added CHECK constraints for all cost fields and date validation
- **Code Updates**: Updated SQLAlchemy model, backend validation, and frontend to match new schema
- **Referential Integrity Preserved**: All foreign keys and downstream tables (donation_item, dnintake, donation_doc) remain functional
- **Migration File**: `migrations/migrate_donation_table_to_target_ddl.sql`

### Item Category Table Enhanced with GOODS/FUNDS Classification
- **Schema Migration**: Added `category_type` column to `itemcatg` table
  - New field: `category_type CHAR(5) NOT NULL` with check constraint for 'GOODS' or 'FUNDS'
  - Default value: 'GOODS' (applied to all existing categories)
  - All 9 existing categories (Food, Water, Hygiene, Medical, Shelter, Clothing, Construction, Tools, Other) classified as GOODS
- **SQLAlchemy Model Updated**: `ItemCategory` model now includes `category_type` field
- **Referential Integrity Preserved**: All existing data, constraints, and foreign key relationships maintained
- **Migration Approach**: Safe ALTER TABLE operations only (no table recreation)
- **Use Case**: Enables future support for FUNDS category types (monetary donations, financial assistance)
- **Zero Breaking Changes**: All existing code, UI, workflows, and business logic continue functioning normally

### Item Categories Configured

**10 Active Categories:**
- **9 GOODS Categories**: Food, Water, Hygiene, Medical, Shelter, Clothing, Construction, Tools, Other
- **1 FUNDS Category**: FUNDS (category_id=10, category_code='FUNDS', category_type='FUNDS')

**Item Table Status:**
- Item table cleared and ready for data entry
- All category infrastructure in place for both GOODS and FUNDS items
- Dynamic donation workflow ready to handle both category types

### Dynamic GOODS/FUNDS Donation Workflow Implemented
- **Category-Driven Behavior**: Donation form dynamically adapts based on item category type (GOODS/FUNDS)
- **API Endpoint**: New `/donations/api/item/<item_id>/category` endpoint fetches item category information via AJAX
- **Auto-Set Donation Type**: JavaScript automatically sets donation_type field (read-only) based on selected item's category
- **Dynamic Field Control**:
  - **GOODS items**: All cost fields editable (item_cost >= 0, addon_cost >= 0, quantity >= 0)
  - **FUNDS items**: addon_cost field disabled and forced to 0.00 (item_cost > 0, addon_cost = 0, quantity >= 0)
- **Help Text Integration**: Cost definition tooltips displayed from `itemcostdef` table without inline styles
- **Aligned Validations**: Frontend, backend, and database constraints synchronized (quantity >= 0 for both types)
- **Clean Payload Handling**: Hidden form inputs use explicit numeric formatting (Number().toFixed(2)) to prevent Decimal parsing errors
- **Security Maintained**: All enterprise security features preserved (CSP with nonces, CSRF protection, no inline styles/handlers)
- **User Experience**: Seamless category-type switching with instant field toggling and validation feedback

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
- **Donation Processing**: Manages full workflow for donations, including intake, verification, batch-level tracking, expiry dates, and integration with warehouse inventory. Supports full donation workflow with country, currency, and cost breakdowns, including document uploads and robust validation.
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Includes an enhanced `public.user` table, a new `itembatch` table (FEFO/FIFO), `itemcostdef` for cost types, `donation_doc` for document attachments, and composite primary keys.
- **Data Flow Patterns**: Supports end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing.
- **Role-Based Access Control (RBAC)**: Centralized feature registry, dynamic navigation, security decorators, smart routing, and a defined role hierarchy. Features secure user management with role assignment restrictions and both client-side and server-side validation.
- **Security Features**: Strict nonce-based Content Security Policy (CSP), comprehensive Flask-WTF Cross-Site Request Forgery (CSRF) Protection, secure cookie configuration (Secure, HttpOnly, SameSite=Lax), Subresource Integrity (SRI) for CDN assets, global no-cache headers for sensitive pages, HTTP header sanitization, production-safe error handling, email obfuscation, query string protection for sensitive parameters, and robust login authentication.
- **Timezone Standardization**: All datetime operations, database timestamps, audit trails, and user-facing displays use Jamaica Standard Time (UTC-05:00).
- **Key Features**: Universal visibility for approved relief requests, accurate inventory validation, batch-level reservation synchronization for draft packages, and automatic inventory table updates on dispatch. Relief package cancellation includes full reservation rollback using optimistic locking and transactional integrity. Implements robust relief request status management.

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