-- ============================================================================
-- ITEM TABLE MIGRATION SCRIPT
-- Purpose: Align existing item table with authoritative schema
-- Date: 2025-11-17
-- ============================================================================

-- Begin transaction for safety
BEGIN;

-- ============================================================================
-- STEP 1: ADD MISSING COLUMNS
-- ============================================================================

-- Add item_code column (required, unique, uppercase)
ALTER TABLE item 
ADD COLUMN item_code varchar(16);

-- Populate item_code with a unique value based on item_id (temporary)
-- You may need to update this with actual business logic
UPDATE item 
SET item_code = 'ITEM-' || LPAD(item_id::text, 10, '0')
WHERE item_code IS NULL;

-- Make item_code NOT NULL after populating
ALTER TABLE item 
ALTER COLUMN item_code SET NOT NULL;

-- Add item_code constraints (will add unique constraint later after dropping old one)
ALTER TABLE item 
ADD CONSTRAINT c_item_1a CHECK (item_code = upper(item_code));

-- Add units_size_vary_flag
ALTER TABLE item 
ADD COLUMN units_size_vary_flag boolean NOT NULL DEFAULT FALSE;

-- Add is_batched_flag
ALTER TABLE item 
ADD COLUMN is_batched_flag boolean NOT NULL DEFAULT TRUE;

-- Add can_expire_flag (replaces expiration_apply_flag conceptually)
ALTER TABLE item 
ADD COLUMN can_expire_flag boolean NOT NULL DEFAULT FALSE;

-- Migrate data from expiration_apply_flag to can_expire_flag
UPDATE item 
SET can_expire_flag = expiration_apply_flag;

-- Add issuance_order
ALTER TABLE item 
ADD COLUMN issuance_order varchar(20) NOT NULL DEFAULT 'FIFO';

-- ============================================================================
-- STEP 2: UPDATE CATEGORY_ID TO NOT NULL
-- ============================================================================

-- First, ensure all category_id values are populated
-- If any are NULL, you need to set them to a valid category_id
-- Check if there are any NULL values first
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM item WHERE category_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot proceed: item table has NULL category_id values. Please populate them first.';
    END IF;
END $$;

-- Make category_id NOT NULL
ALTER TABLE item 
ALTER COLUMN category_id SET NOT NULL;

-- ============================================================================
-- STEP 3: RENAME/UPDATE EXISTING CONSTRAINTS
-- ============================================================================

-- Drop old unique constraints that are named incorrectly
ALTER TABLE item DROP CONSTRAINT IF EXISTS uk_item_1;
ALTER TABLE item DROP CONSTRAINT IF EXISTS uk_item_2;

-- Add new unique constraints with correct naming
ALTER TABLE item ADD CONSTRAINT uk_item_1 UNIQUE (item_code);
ALTER TABLE item ADD CONSTRAINT uk_item_2 UNIQUE (item_name);
ALTER TABLE item ADD CONSTRAINT uk_item_3 UNIQUE (sku_code);

-- Rename existing check constraints to match target naming
ALTER TABLE item DROP CONSTRAINT IF EXISTS item_item_name_check;
ALTER TABLE item ADD CONSTRAINT c_item_1b CHECK (item_name = upper(item_name));

ALTER TABLE item DROP CONSTRAINT IF EXISTS item_sku_code_check;
ALTER TABLE item ADD CONSTRAINT c_item_1c CHECK (sku_code = upper(sku_code));

ALTER TABLE item DROP CONSTRAINT IF EXISTS item_reorder_qty_check;
ALTER TABLE item ADD CONSTRAINT c_item_1d CHECK (reorder_qty > 0.00);

ALTER TABLE item DROP CONSTRAINT IF EXISTS item_status_code_check;
ALTER TABLE item ADD CONSTRAINT c_item_3 CHECK (status_code in ('A','I'));

-- Rename foreign key constraints
ALTER TABLE item DROP CONSTRAINT IF EXISTS item_category_id_fkey;
ALTER TABLE item ADD CONSTRAINT fk_item_itemcatg 
    FOREIGN KEY (category_id) REFERENCES itemcatg(category_id);

ALTER TABLE item DROP CONSTRAINT IF EXISTS item_default_uom_code_fkey;
ALTER TABLE item ADD CONSTRAINT fk_item_unitofmeasure 
    FOREIGN KEY (default_uom_code) REFERENCES unitofmeasure(uom_code);

-- ============================================================================
-- STEP 4: DROP OBSOLETE COLUMNS
-- ============================================================================

-- Drop category_code (replaced by category_id foreign key)
ALTER TABLE item DROP COLUMN IF EXISTS category_code;

-- Drop expiration_apply_flag (replaced by can_expire_flag)
ALTER TABLE item DROP COLUMN IF EXISTS expiration_apply_flag;

-- ============================================================================
-- STEP 5: CREATE MISSING INDEXES
-- ============================================================================

-- dk_item_1 already exists on item_desc
-- Create dk_item_2 on category_id
CREATE INDEX IF NOT EXISTS dk_item_2 ON item(category_id);

-- Create dk_item_3 on sku_code
CREATE INDEX IF NOT EXISTS dk_item_3 ON item(sku_code);

-- ============================================================================
-- STEP 6: ENSURE TIMESTAMP PRECISION
-- ============================================================================

-- Set timestamp precision to 0 for create_dtime and update_dtime
ALTER TABLE item 
ALTER COLUMN create_dtime TYPE timestamp(0) without time zone;

ALTER TABLE item 
ALTER COLUMN update_dtime TYPE timestamp(0) without time zone;

-- ============================================================================
-- STEP 7: VERIFY PRIMARY KEY
-- ============================================================================

-- Ensure primary key constraint is named correctly
ALTER TABLE item DROP CONSTRAINT IF EXISTS item_pkey;
ALTER TABLE item ADD CONSTRAINT pk_item PRIMARY KEY (item_id);

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Run these queries after the migration to verify success:

-- 1. Check all columns exist with correct data types
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'item'
ORDER BY ordinal_position;

-- 2. Check all constraints exist
SELECT
    constraint_name,
    constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'item'
ORDER BY constraint_type, constraint_name;

-- 3. Check all indexes exist
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'item'
ORDER BY indexname;

-- 4. Verify data integrity
SELECT 
    COUNT(*) as total_rows,
    COUNT(DISTINCT item_code) as unique_item_codes,
    COUNT(DISTINCT item_name) as unique_item_names,
    COUNT(DISTINCT sku_code) as unique_sku_codes
FROM item;
