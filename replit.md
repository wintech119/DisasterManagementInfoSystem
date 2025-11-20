# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

## Recent Changes (November 20, 2025)
- **Navigation Consolidation**: Removed duplicate "Create Relief Requests" menu item. Retained single "Create Request (On Behalf of Agency)" option accessible to all authorized users (both logistics and agency roles).
- **Multi-Role Request Creation**: Updated `packaging.create_request_on_behalf` to support both LOGISTICS users (select any agency) and AGENCY users (auto-bound to their own agency).
- **Template Enhancements**: Updated create request template with conditional rendering based on user type - logistics users see agency dropdown, agency users see read-only agency field.
- **LM/LO Relief Request Navigation Update**: Updated navigation workflow for Logistics Managers and Logistics Officers. Sidebar menu "Create Request (On Behalf of Agency)" now navigates to the Relief Requests list page (showing all requests). Page title renamed to "Relief Requests on Behalf of Agency" for LM/LO only; agency users still see "Relief Requests". "New Request" button on list page routes to the on-behalf form (`packaging.create_request_on_behalf`) for LM/LO, standard form for agencies. Updated "Back" and "Cancel" buttons on Create Request (On Behalf of Agency) form to return to Relief Requests list page instead of Pending Fulfillment queue. Maintains distinct user experiences while consolidating navigation.
- **Dashboard Fixes**: Corrected Item model column references in inventory dashboard (`reorder_level` → `reorder_qty`). Removed inventory value calculation due to absence of cost data in schema.
- **Donation Intake Form Updates**: 
  - Enforced 2 decimal places max for quantity fields (Usable, Defective, Expired), removed spinner arrows from all numeric inputs, added Unit Cost 8.2 format cap (max 99,999,999.99) with JavaScript validation.
  - Implemented dynamic usable quantity adjustment: Usable Qty auto-calculates in real-time as `Donated Qty - Defective - Expired` when defective/expired values change. Field is read-only with visual indication (light gray background).
  - Updated validation rules on form to clearly reflect dynamic field behavior.
- **Phone Number Field Standardization**: Aligned phone number field format between Creating Agency and Creating Donor forms. Both now use `phone-mask.js` for consistent formatting with pattern `+1 (XXX) XXX-XXXX`. Applied to both create and edit templates.
- **Database Schema Fix**: Created missing `transfer_item` table that was dropped in migration 007 but never recreated. Added all required columns including `reason_text` to match the TransferItem model. Fixed issue preventing item status changes (activate/inactivate) and UOM detail page errors. Migration 008 applied successfully with subsequent column addition.
- **Processed Donation Protection**: Implemented complete protection against editing processed donations (status 'P'). Added server-side validation to prevent editing, adding items, or deleting processed donations since they're already in warehouse inventory. Updated view template to hide all edit/delete buttons and display lock icon for processed donations. Ensures data integrity by preventing modifications to donations that have been integrated into the warehouse system.
- **Relief Package Request Locking (LO/LM)**: Implemented complete access blocking for locked relief requests during package preparation. When an LO or LM opens a relief request for preparation (via queue or notification deeplink), the system acquires an exclusive lock. Any other LO/LM attempting to access the same request is immediately blocked with a clear message showing who is currently preparing it. Lock is released when user submits, cancels, or completes preparation. Prevents concurrent editing conflicts and ensures data integrity during package fulfillment workflow.
- **Save Draft Lock Release Enhancement**: Updated Save Draft functionality for both LO and LM workflows to automatically release fulfillment locks after successful save. When an LO saves draft allocations, the lock is immediately released and user is redirected to Pending Fulfillment queue, allowing other LO/LM users to continue editing the package. Similarly, when an LM saves draft allocations, the lock is released and user is redirected to Pending Approval queue. Lock is retained only on save failures (insufficient inventory, validation errors) so users can continue editing. Inventory reservations remain intact when lock is released, ensuring allocated quantities are protected. This collaborative approach enables team-based package preparation while maintaining data integrity.
- **Warehouse-Based Batch Filtering and Sorting**: Enhanced Select Batches drawer to implement intelligent warehouse-specific logic. Only warehouses with available inventory (usable_qty - reserved_qty > 0) are shown. Batches are grouped by warehouse and sorted within each warehouse using FEFO (earliest expiry first) for expirable items or FIFO (oldest batch first) for non-expirable items. Early stopping per warehouse: loading stops once cumulative quantity from that warehouse meets or exceeds remaining quantity, including allocated batches. Previously allocated batches are always included for editing. This provides users with the minimum necessary batches from each warehouse while maintaining proper FEFO/FIFO sequencing.
- **Approved Package Tab Filter Fix**: Fixed issue where approved relief requests (status='D' dispatched) were incorrectly appearing in the "Being Prepared" tab after LM approval. Added `has_dispatched_package()` helper function to identify requests with dispatched packages. Updated both "Awaiting" and "Being Prepared" tab filters to exclude requests with dispatched packages, ensuring they only appear in the "Approved for Dispatch" tab. Also updated badge count calculations to reflect the corrected filtering logic. This ensures proper workflow separation and prevents confusion about package status.
- **Empty Package Dispatch Prevention**: Fixed critical data integrity issue where packages could be approved and dispatched without any items in the `reliefpkg_item` table. Deleted two problematic empty packages (IDs 11, 14) that were invisible to Inventory Officers. Implemented comprehensive validation in both approval workflows (`_approve_and_dispatch` and `review_approval`) to prevent empty package dispatch: (1) Verifies `ReliefPkgItem` records exist before dispatch, (2) Validates that sum of `ReliefPkgItem` quantities matches each `reliefrqst_item.issue_qty` for data integrity, (3) Allows dispatch when ALL items have unavailability statuses (U, D, W) even with zero allocations, (4) Detects and blocks dispatch when `issue_qty > 0` but no corresponding `ReliefPkgItem` records exist (data drift scenarios), (5) Provides clear error messages guiding users to re-prepare packages when data mismatches occur. This ensures Inventory Officers can see all valid dispatched packages in their warehouse-filtered queues and prevents data inconsistencies between allocation records and issue quantities.
- **Approved Packages Tab Separation**: Added new "Approved (No Allocation)" tab for Logistics Managers to view packages approved with zero items allocated. Updated filtering logic to split approved packages into two categories: "Approved for Dispatch" (packages WITH items allocated) and "Approved (No Allocation)" (packages with NO items allocated, all marked as unavailable/denied/waiting). New tab displays Request ID, Agency, Requested Items count, LM Approver, Approval Date, and Reason. Updated global badge counts to reflect both categories separately. This provides better visibility into packages that were legitimately approved despite zero allocation due to item unavailability.

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
The application employs a modular blueprint architecture with a database-first approach, built upon a pre-existing ODPEM `aidmgmt-3.sql` schema. Key architectural decisions and features include:
-   **UI/UX Design**: Emphasizes a consistent modern UI, comprehensive design system, shared Jinja2 components, GOJ branding, accessibility (WCAG 2.1 AA), and standardized workflow patterns. It features role-specific dashboards and complete management modules for various entities with CRUD operations, validation, and optimistic locking.
-   **Notification System**: Includes real-time in-app notifications with badge counters, offcanvas panels, deep-linking, read/unread tracking, and bulk operations.
-   **Donation Processing**: Manages the full workflow for donations, including intake, verification, batch-level tracking, expiry date management, and integration with warehouse inventory.
-   **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table.
-   **Data Flow Patterns**: Supports an end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities.
-   **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Features secure user management with role assignment restrictions to prevent privilege escalation: CUSTODIAN users can manage operational users but cannot assign administrative roles (SYSTEM_ADMINISTRATOR, SYS_ADMIN); includes both client-side role filtering and server-side validation to prevent bypass attacks.
- **Timezone Standardization**: All datetime operations, database timestamps, audit trails, and user-facing displays use Jamaica Standard Time (UTC-05:00) consistently.

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