# DRIMS - Disaster Relief Inventory Management System

## Overview
DRIMS (Disaster Relief Inventory Management System) is a web-based platform for the Government of Jamaica's ODPEM, designed to manage the entire lifecycle of disaster relief supplies. This includes inventory tracking, donation management, relief request processing, and distribution across multiple warehouses. The system aims to ensure compliance with government processes, support disaster event coordination, supply allocation, and provide robust user administration with Role-Based Access Control (RBAC). Its core purpose is to deliver a modern, efficient, and user-friendly solution for disaster preparedness and response, emphasizing security and comprehensive management capabilities such as inventory transfers, location tracking, analytics, and reporting.

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
- **Database Architecture**: Based on a 40-table ODPEM schema, ensuring data consistency, auditability, precision, and optimistic locking. Features an enhanced `public.user` table, a new `itembatch` table for batch-level inventory (FEFO/FIFO), and a composite primary key for the `inventory` table.
- **Data Flow Patterns**: Supports an end-to-end AIDMGMT Relief Workflow, role-based dashboards, two-tier inventory management, eligibility approval, and package fulfillment with batch-level editing capabilities.
- **Role-Based Access Control (RBAC)**: Implemented through a centralized feature registry, dynamic navigation, security decorators, smart routing based on primary roles, and a defined role hierarchy. Features secure user management with role assignment restrictions to prevent privilege escalation; includes both client-side role filtering and server-side validation to prevent bypass attacks.
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