-- ============================================================================
-- ITEM TABLE PRE-MIGRATION VALIDATION SCRIPT
-- Purpose: Check data integrity before running migration
-- Date: 2025-11-17
-- ============================================================================

-- Check 1: Verify all category_id values are populated
SELECT 
    'Category ID Check' as check_name,
    COUNT(*) as total_rows,
    COUNT(category_id) as populated_category_ids,
    COUNT(*) - COUNT(category_id) as null_category_ids
FROM item;

-- If null_category_ids > 0, you need to populate them before migration
-- Example fix (customize as needed):
-- UPDATE item SET category_id = 1 WHERE category_id IS NULL;

-- Check 2: Verify all items have unique names and SKUs
SELECT 
    'Uniqueness Check' as check_name,
    COUNT(*) as total_rows,
    COUNT(DISTINCT item_name) as unique_names,
    COUNT(DISTINCT sku_code) as unique_skus,
    CASE 
        WHEN COUNT(*) = COUNT(DISTINCT item_name) THEN 'PASS' 
        ELSE 'FAIL - Duplicate item_name exists' 
    END as name_uniqueness,
    CASE 
        WHEN COUNT(*) = COUNT(DISTINCT sku_code) THEN 'PASS' 
        ELSE 'FAIL - Duplicate sku_code exists' 
    END as sku_uniqueness
FROM item;

-- Check 3: Find any duplicate item names
SELECT 
    item_name,
    COUNT(*) as duplicate_count
FROM item
GROUP BY item_name
HAVING COUNT(*) > 1;

-- Check 4: Find any duplicate SKU codes
SELECT 
    sku_code,
    COUNT(*) as duplicate_count
FROM item
GROUP BY sku_code
HAVING COUNT(*) > 1;

-- Check 5: Verify reorder_qty is always > 0
SELECT 
    'Reorder Qty Check' as check_name,
    COUNT(*) as total_rows,
    COUNT(*) FILTER (WHERE reorder_qty > 0) as valid_reorder_qty,
    COUNT(*) FILTER (WHERE reorder_qty <= 0) as invalid_reorder_qty
FROM item;

-- Check 6: Verify status_code values
SELECT 
    'Status Code Check' as check_name,
    status_code,
    COUNT(*) as count
FROM item
GROUP BY status_code
ORDER BY status_code;

-- Check 7: Preview proposed item_code values (auto-generated)
SELECT 
    item_id,
    item_name,
    sku_code,
    'ITEM-' || LPAD(item_id::text, 10, '0') as proposed_item_code
FROM item
ORDER BY item_id
LIMIT 10;

-- ============================================================================
-- IMPORTANT NOTES FOR ITEM_CODE POPULATION
-- ============================================================================
-- The migration script will auto-generate item_code as 'ITEM-0000000001', etc.
-- 
-- If you want to use custom item codes instead, run this BEFORE the migration:
-- 
-- UPDATE item SET item_code = '<your_business_logic>' WHERE condition;
-- 
-- Example: Use SKU code as item code if they're the same:
-- UPDATE item SET item_code = sku_code;
-- 
-- Or use a combination:
-- UPDATE item SET item_code = 'ITM-' || sku_code;
-- ============================================================================
