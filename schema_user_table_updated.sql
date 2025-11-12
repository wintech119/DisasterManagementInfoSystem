-- ================================================================
-- DRIMS User Table - Complete Schema (Updated November 12, 2025)
-- ================================================================
-- This schema includes MFA, account lockout, password management,
-- agency linkage, status tracking, and optimistic locking support.
-- ================================================================

-- Enable citext extension for case-insensitive email comparison
CREATE EXTENSION IF NOT EXISTS citext;

-- Create sequence for user IDs
CREATE SEQUENCE IF NOT EXISTS user_id_seq;

-- ================================================================
-- TABLE: public.user
-- ================================================================
-- Main user authentication and account management table
-- Supports MFA, lockout controls, and comprehensive auditing
-- ================================================================

CREATE TABLE IF NOT EXISTS public."user" (
    -- Core Identity
    id integer NOT NULL DEFAULT nextval('user_id_seq'::regclass),
    email varchar(200) NOT NULL,
    username varchar(60),
    
    -- Authentication
    password_hash varchar(256) NOT NULL,
    password_algo varchar(20) NOT NULL DEFAULT 'argon2id',
    password_changed_at timestamp(0) without time zone,
    
    -- Multi-Factor Authentication
    mfa_enabled boolean NOT NULL DEFAULT false,
    mfa_secret varchar(64),
    
    -- Account Security & Lockout
    failed_login_count smallint NOT NULL DEFAULT 0,
    lock_until_at timestamp(0) without time zone,
    status_code char(1) NOT NULL DEFAULT 'A',  -- A=Active, I=Inactive, L=Locked
    
    -- Profile Information
    first_name varchar(100),
    last_name varchar(100),
    full_name varchar(200),
    role varchar(50),
    organization varchar(200),
    job_title varchar(200),
    phone varchar(50),
    
    -- System Settings
    is_active boolean NOT NULL DEFAULT true,
    timezone varchar(50) NOT NULL DEFAULT 'America/Jamaica',
    language varchar(10) NOT NULL DEFAULT 'en',
    notification_preferences text,
    
    -- Relationships
    assigned_warehouse_id integer,
    agency_id integer,
    
    -- Audit Fields
    created_at timestamp(0) without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp(0) without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id integer,
    updated_by_id integer,
    last_login_at timestamp(0) without time zone,
    
    -- Optimistic Locking
    version_nbr integer NOT NULL DEFAULT 1
);

-- ================================================================
-- PRIMARY KEY
-- ================================================================

ALTER TABLE public."user" 
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);

-- ================================================================
-- UNIQUE CONSTRAINTS
-- ================================================================

ALTER TABLE public."user" 
    ADD CONSTRAINT user_email_key UNIQUE (email);

-- ================================================================
-- CHECK CONSTRAINTS
-- ================================================================

-- Status code must be A (Active), I (Inactive), or L (Locked)
ALTER TABLE public."user" 
    ADD CONSTRAINT c_user_status_code 
    CHECK (status_code IN ('A', 'I', 'L'));

-- ================================================================
-- FOREIGN KEY CONSTRAINTS
-- ================================================================

-- Link to agency table
ALTER TABLE public."user" 
    ADD CONSTRAINT user_agency_id_fkey 
    FOREIGN KEY (agency_id) REFERENCES agency(agency_id);

-- Link to warehouse table
ALTER TABLE public."user" 
    ADD CONSTRAINT user_assigned_warehouse_id_fkey 
    FOREIGN KEY (assigned_warehouse_id) REFERENCES warehouse(warehouse_id);

-- Self-referencing for audit trail
ALTER TABLE public."user" 
    ADD CONSTRAINT user_created_by_id_fkey 
    FOREIGN KEY (created_by_id) REFERENCES "user"(id);

ALTER TABLE public."user" 
    ADD CONSTRAINT user_updated_by_id_fkey 
    FOREIGN KEY (updated_by_id) REFERENCES "user"(id);

-- ================================================================
-- INDEXES
-- ================================================================

-- Unique index on username for alternative login
CREATE UNIQUE INDEX IF NOT EXISTS uk_user_username 
    ON public."user"(username);

-- Index on email for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_email 
    ON public."user"(email);

-- Index on agency_id for relationship queries
CREATE INDEX IF NOT EXISTS dk_user_agency_id 
    ON public."user"(agency_id);

-- ================================================================
-- TRIGGER FUNCTION: Auto-update timestamp
-- ================================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$function$;

-- ================================================================
-- TRIGGER: Auto-update updated_at on modifications
-- ================================================================

DROP TRIGGER IF EXISTS trg_user_set_updated_at ON public."user";

CREATE TRIGGER trg_user_set_updated_at
    BEFORE UPDATE ON public."user"
    FOR EACH ROW
    EXECUTE PROCEDURE set_updated_at();

-- ================================================================
-- COMMENTS (Optional - for documentation)
-- ================================================================

COMMENT ON TABLE public."user" IS 'User authentication and account management with MFA and lockout support';
COMMENT ON COLUMN public."user".mfa_enabled IS 'Multi-factor authentication enabled flag';
COMMENT ON COLUMN public."user".mfa_secret IS 'Encrypted MFA secret for TOTP generation';
COMMENT ON COLUMN public."user".failed_login_count IS 'Counter for failed login attempts';
COMMENT ON COLUMN public."user".lock_until_at IS 'Timestamp until which account is locked';
COMMENT ON COLUMN public."user".status_code IS 'Account status: A=Active, I=Inactive, L=Locked';
COMMENT ON COLUMN public."user".version_nbr IS 'Optimistic locking version number';
COMMENT ON COLUMN public."user".password_algo IS 'Password hashing algorithm (default: argon2id)';
COMMENT ON COLUMN public."user".agency_id IS 'Foreign key to agency table for organizational linking';

-- ================================================================
-- END OF SCHEMA
-- ================================================================
