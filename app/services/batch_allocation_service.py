"""
Batch Allocation Service - FEFO/FIFO allocation logic for relief packages

Supports First Expired First Out (FEFO) for expirable items and
First In First Out (FIFO) for non-expirable items based on item configuration.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app.db import db
from app.db.models import Item, ItemBatch, Inventory, Warehouse


class BatchAllocationService:
    """Service for managing batch-level allocations with FEFO/FIFO rules"""
    
    @staticmethod
    def get_available_batches(item_id: int, warehouse_id: int = None, required_uom: str = None) -> List[ItemBatch]:
        """
        Get available batches for an item, optionally filtered by warehouse and UOM.
        
        Args:
            item_id: Item to get batches for
            warehouse_id: Optional warehouse filter
            required_uom: Optional UOM filter (matches request UOM)
            
        Returns:
            List of ItemBatch objects with available quantity > 0
        """
        query = ItemBatch.query.options(
            joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse),
            joinedload(ItemBatch.item),
            joinedload(ItemBatch.uom)
        ).join(
            Inventory,
            and_(
                ItemBatch.inventory_id == Inventory.inventory_id,
                ItemBatch.item_id == Inventory.item_id
            )
        ).join(
            Warehouse,
            Inventory.inventory_id == Warehouse.warehouse_id
        ).filter(
            ItemBatch.item_id == item_id,
            ItemBatch.status_code == 'A',
            Inventory.status_code == 'A',
            Warehouse.status_code == 'A',
            ItemBatch.usable_qty > ItemBatch.reserved_qty
        )
        
        if warehouse_id:
            query = query.filter(Inventory.inventory_id == warehouse_id)
        
        if required_uom:
            query = query.filter(ItemBatch.uom_code == required_uom)
        
        return query.all()
    
    @staticmethod
    def sort_batches_for_drawer(batches: List[ItemBatch], item: Item, skip_availability_filter: bool = False) -> List[ItemBatch]:
        """
        Sort batches for drawer display based ONLY on can_expire_flag.
        Ignores item.issuance_order field to ensure consistent FEFO/FIFO behavior.
        
        Drawer Sorting Rules (per warehouse):
        - If can_expire_flag = TRUE: Sort by earliest expiry_date, then oldest batch_date
        - If can_expire_flag = FALSE: Sort by oldest batch_date (FIFO)
        
        Args:
            batches: List of batches to sort
            item: Item object with can_expire_flag
            skip_availability_filter: If True, don't filter out zero-available batches
                                      (used for Set A allocated batches that must always be shown)
            
        Returns:
            Sorted list of batches
        """
        today = date.today()
        
        # Filter out expired batches if item can expire
        # NULL expiry dates are treated as "never expires" and are allowed
        if item.can_expire_flag:
            active_batches = [
                b for b in batches 
                if not b.expiry_date or b.expiry_date >= today
            ]
        else:
            active_batches = batches
        
        # Filter out batches with zero available quantity
        # UNLESS skip_availability_filter is True (for Set A allocated batches)
        # CRITICAL: ALWAYS use _released_available (must be attached before calling this function)
        if not skip_availability_filter:
            active_batches = [
                b for b in active_batches 
                if b._released_available > 0
            ]
        
        # Sort based ONLY on can_expire_flag (ignore issuance_order)
        if item.can_expire_flag:
            # FEFO: Sort by earliest expiry date, then oldest batch date
            return sorted(
                active_batches,
                key=lambda b: (
                    b.expiry_date is None,  # NULL expiry dates go to end
                    b.expiry_date if b.expiry_date else date.max, 
                    b.batch_date if b.batch_date else date.max
                )
            )
        else:
            # FIFO: Sort by oldest batch date
            return sorted(
                active_batches, 
                key=lambda b: (
                    b.batch_date if b.batch_date else date.min
                )
            )
    
    @staticmethod
    def sort_batches_by_allocation_rule(batches: List[ItemBatch], item: Item) -> List[ItemBatch]:
        """
        Sort batches according to FEFO/FIFO rules based on item configuration.
        Includes deterministic tie-breaker on usable_qty DESC.
        
        Args:
            batches: List of batches to sort
            item: Item object with issuance_order and can_expire_flag
            
        Returns:
            Sorted list of batches with priority group assignments
        """
        today = date.today()
        
        # Filter out expired batches if item can expire
        # NULL expiry dates are treated as "never expires" and are allowed
        if item.can_expire_flag:
            active_batches = [
                b for b in batches 
                if not b.expiry_date or b.expiry_date >= today
            ]
        else:
            active_batches = batches
        
        # Filter out batches with zero available quantity
        # Only show warehouses/batches that have actual usable stock
        active_batches = [
            b for b in active_batches 
            if (b.usable_qty - b.reserved_qty) > 0
        ]
        
        # Sort based on issuance order with tie-breakers
        if item.issuance_order == 'FEFO' and item.can_expire_flag:
            # First Expired First Out - sort by earliest expiry date, then batch date, then qty DESC
            return sorted(
                active_batches,
                key=lambda b: (
                    b.expiry_date is None, 
                    b.expiry_date if b.expiry_date else date.max, 
                    b.batch_date if b.batch_date else date.max,
                    -(b.usable_qty - b.reserved_qty)  # Negative for DESC
                )
            )
        elif item.issuance_order == 'LIFO':
            # Last In First Out - sort by latest batch date, then qty DESC
            return sorted(
                active_batches, 
                key=lambda b: (
                    -(b.batch_date.toordinal() if b.batch_date else 0),
                    -(b.usable_qty - b.reserved_qty)
                )
            )
        else:  # FIFO (default)
            # First In First Out - sort by earliest batch date, then qty DESC
            return sorted(
                active_batches, 
                key=lambda b: (
                    b.batch_date if b.batch_date else date.min,
                    -(b.usable_qty - b.reserved_qty)
                )
            )
    
    @staticmethod
    def auto_allocate_batches(
        item_id: int,
        requested_qty: Decimal,
        warehouse_id: int = None
    ) -> List[Dict]:
        """
        Auto-allocate batches for an item following FEFO/FIFO rules.
        
        Args:
            item_id: Item to allocate
            requested_qty: Total quantity to allocate
            warehouse_id: Optional warehouse filter
            
        Returns:
            List of allocation dicts with keys:
                - batch_id: Batch ID
                - batch_no: Batch number
                - warehouse_id: Warehouse ID
                - warehouse_name: Warehouse name
                - inventory_id: Inventory ID
                - batch_date: Batch date
                - expiry_date: Expiry date (if any)
                - available_qty: Available quantity in batch
                - allocated_qty: Quantity allocated from this batch
                - uom_code: Unit of measure
        """
        # Get item to check allocation rules
        item = Item.query.get(item_id)
        if not item:
            return []
        
        # Get available batches
        batches = BatchAllocationService.get_available_batches(item_id, warehouse_id)
        
        # Sort by allocation rule
        sorted_batches = BatchAllocationService.sort_batches_by_allocation_rule(batches, item)
        
        # Allocate quantities
        allocations = []
        remaining_qty = Decimal(str(requested_qty))
        
        for batch in sorted_batches:
            if remaining_qty <= 0:
                break
            
            available_qty = batch.usable_qty - batch.reserved_qty
            allocated_qty = min(available_qty, remaining_qty)
            
            if allocated_qty > 0:
                allocations.append({
                    'batch_id': batch.batch_id,
                    'batch_no': batch.batch_no,
                    'warehouse_id': batch.inventory.inventory_id,
                    'warehouse_name': batch.inventory.warehouse.warehouse_name,
                    'inventory_id': batch.inventory_id,
                    'batch_date': batch.batch_date,
                    'expiry_date': batch.expiry_date,
                    'available_qty': float(available_qty),
                    'allocated_qty': float(allocated_qty),
                    'uom_code': batch.uom_code,
                    'size_spec': batch.size_spec
                })
                remaining_qty -= allocated_qty
        
        return allocations
    
    @staticmethod
    def get_batch_details(batch_id: int) -> Optional[Dict]:
        """
        Get detailed information about a specific batch.
        
        Args:
            batch_id: Batch ID
            
        Returns:
            Dict with batch details or None if not found
        """
        batch = ItemBatch.query.options(
            joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse),
            joinedload(ItemBatch.item),
            joinedload(ItemBatch.uom)
        ).get(batch_id)
        
        if not batch:
            return None
        
        available_qty = batch.usable_qty - batch.reserved_qty
        is_expired = batch.expiry_date and batch.expiry_date < date.today() if batch.expiry_date else False
        
        return {
            'batch_id': batch.batch_id,
            'batch_no': batch.batch_no,
            'warehouse_id': batch.inventory.inventory_id,
            'warehouse_name': batch.inventory.warehouse.warehouse_name,
            'inventory_id': batch.inventory_id,
            'item_id': batch.item_id,
            'item_name': batch.item.item_name,
            'batch_date': batch.batch_date,
            'expiry_date': batch.expiry_date,
            'usable_qty': float(batch.usable_qty),
            'reserved_qty': float(batch.reserved_qty),
            'available_qty': float(available_qty),
            'defective_qty': float(batch.defective_qty),
            'expired_qty': float(batch.expired_qty),
            'uom_code': batch.uom_code,
            'size_spec': batch.size_spec,
            'status_code': batch.status_code,
            'is_expired': is_expired
        }
    
    @staticmethod
    def validate_batch_allocation(
        batch_id: int,
        item_id: int,
        allocated_qty: Decimal,
        current_allocated_qty: Decimal = Decimal('0')
    ) -> Tuple[bool, str]:
        """
        Validate a batch allocation.
        
        When re-allocating from an existing package, the current package's allocation
        is "released" from reserved_qty to calculate true availability. This allows
        users to modify their existing allocations without false "no inventory" errors.
        
        Args:
            batch_id: Batch ID to allocate from
            item_id: Item being allocated
            allocated_qty: Quantity to allocate
            current_allocated_qty: Current allocation from this package for this batch (default: 0)
                                   This qty is "released" from reserved_qty when calculating availability
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        batch = ItemBatch.query.get(batch_id)
        
        if not batch:
            return False, f'Batch {batch_id} not found'
        
        if batch.item_id != item_id:
            return False, f'Batch {batch_id} does not contain item {item_id}'
        
        if batch.status_code != 'A':
            return False, f'Batch {batch.batch_no} is not available (status: {batch.status_code})'
        
        # Check expiry
        if batch.expiry_date and batch.expiry_date < date.today():
            return False, f'Batch {batch.batch_no} is expired (expiry: {batch.expiry_date})'
        
        # Check quantity
        # CRITICAL: "Release" current package's allocation when calculating availability
        # This prevents false "no inventory" errors when re-allocating from existing packages
        available_qty = batch.usable_qty - (batch.reserved_qty - current_allocated_qty)
        if allocated_qty > available_qty:
            if available_qty <= 0:
                return False, (f'Batch {batch.batch_no} has no available inventory (all {batch.usable_qty} units are reserved or allocated). '
                             f'This may occur if another user allocated from this batch while you were working. '
                             f'Please refresh the page and select a different batch with available stock.')
            else:
                return False, (f'Batch {batch.batch_no} has only {available_qty:.4f} units available, cannot allocate {allocated_qty:.4f}. '
                             f'Please reduce the allocation quantity or select an additional batch.')
        
        if allocated_qty <= 0:
            return False, 'Allocated quantity must be greater than zero'
        
        return True, ''
    
    @staticmethod
    def get_batches_by_warehouse(item_id: int) -> Dict[int, List[ItemBatch]]:
        """
        Get batches grouped by warehouse for an item.
        
        Args:
            item_id: Item ID
            
        Returns:
            Dict mapping warehouse_id to list of batches
        """
        batches = BatchAllocationService.get_available_batches(item_id)
        item = Item.query.get(item_id)
        
        if item:
            batches = BatchAllocationService.sort_batches_by_allocation_rule(batches, item)
        
        warehouse_batches = {}
        for batch in batches:
            wh_id = batch.inventory.inventory_id
            if wh_id not in warehouse_batches:
                warehouse_batches[wh_id] = []
            warehouse_batches[wh_id].append(batch)
        
        return warehouse_batches
    
    @staticmethod
    def get_limited_batches_for_drawer(
        item_id: int,
        requested_qty: Decimal,
        required_uom: str = None,
        allocated_batch_ids: List[int] = None,
        current_allocations: dict = None
    ) -> Tuple[List[ItemBatch], Decimal, Decimal]:
        """
        Get batches for the LM drawer display with enhanced allocation and truncation logic.
        
        This implements the following rules:
        
        SET A (Allocated Batches): Always shown, even if available = 0
        - These are batches already allocated to this (reliefpkg_id, item_id) pair
        - Must always appear in the drawer for editing
        
        SET B (Available Batches): Only shown if available > 0
        - Only include batches where: available = usable_qty - reserved_qty > 0
        - These are potential batches the LM can use for adjustments
        
        Per-Warehouse Sorting:
        - If item can expire: Sort by earliest expiry_date, then oldest batch_date (FEFO)
        - If item cannot expire: Sort by oldest batch_date (FIFO)
        
        Per-Warehouse Truncation:
        - Start with all allocated batches from this warehouse (Set A)
        - Add available-only batches (Set B) until potentialFromWarehouse >= requested_qty
        - This ensures LM sees enough batches to hypothetically fill the entire request 
          from each single warehouse, while never seeing more batches than necessary
        
        Important: When current_allocations is provided, those quantities are "released" from
        reserved_qty when calculating available_qty. This allows LM to re-allocate freely.
        
        Args:
            item_id: Item ID
            requested_qty: Requested quantity for this item on the relief request (NOT remaining)
            required_uom: Required unit of measure
            allocated_batch_ids: List of batch IDs that are already allocated (Set A)
            current_allocations: Dict mapping batch_id -> qty for current package's allocations
                                 (these are "released" from reserved_qty when calculating available)
            
        Returns:
            Tuple of:
                - List of batches (Set A union truncated Set B, per warehouse)
                - Total available from these batches
                - Shortfall (0 if can fulfill, positive if not)
        """
        # Get item
        item = Item.query.get(item_id)
        if not item:
            return [], Decimal('0'), requested_qty
        
        allocated_batch_ids_set = set(allocated_batch_ids or [])
        current_allocations = current_allocations or {}
        
        # Helper function to calculate effective available quantity
        # This "releases" current package's allocations from reserved_qty
        def calc_available_qty(batch):
            released_qty = current_allocations.get(batch.batch_id, Decimal('0'))
            return batch.usable_qty - (batch.reserved_qty - released_qty)
        
        # STEP 1A: Fetch ALL batches for this item (no availability filtering yet)
        # We'll calculate availability AFTER releasing current allocations
        from app.db.models import ItemBatch
        from sqlalchemy.orm import joinedload
        
        all_batches_query = ItemBatch.query.join(
            Inventory,
            and_(
                ItemBatch.inventory_id == Inventory.inventory_id,
                ItemBatch.item_id == Inventory.item_id
            )
        ).join(
            Warehouse,
            Inventory.inventory_id == Warehouse.warehouse_id
        ).filter(
            ItemBatch.item_id == item_id,
            ItemBatch.status_code == 'A',
            Inventory.status_code == 'A',
            Warehouse.status_code == 'A'
        ).options(
            joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse)
        )
        
        if required_uom:
            all_batches_query = all_batches_query.filter(ItemBatch.uom_code == required_uom)
        
        all_batches = all_batches_query.all()
        
        # STEP 1B: Calculate released availability for ALL batches and attach to batch objects
        # This ensures sorting and truncation use the correct post-release values
        for batch in all_batches:
            # Calculate availability AFTER releasing current allocations
            released_available = calc_available_qty(batch)
            # Attach as temporary attribute for downstream use
            batch._released_available = released_available
        
        # STEP 1C: Separate batches into Set A and Set B based on allocation status and released availability
        warehouse_groups = {}
        
        for batch in all_batches:
            warehouse_id = batch.inventory.inventory_id
            
            if warehouse_id not in warehouse_groups:
                warehouse_groups[warehouse_id] = {
                    'allocated_batches': [],  # Set A: Always shown
                    'available_batches': [],  # Set B: Shown only if released available > 0
                    'allocated_qty_sum': Decimal('0')  # Sum of allocated quantities (not available)
                }
            
            is_allocated = batch.batch_id in allocated_batch_ids_set
            released_available = batch._released_available  # Use attached value
            
            # Set A: Allocated batches - ALWAYS include, even if released_available <= 0
            if is_allocated:
                warehouse_groups[warehouse_id]['allocated_batches'].append(batch)
                # Track sum of ALLOCATED quantities (from current_allocations), not available
                allocated_qty = current_allocations.get(batch.batch_id, Decimal('0'))
                warehouse_groups[warehouse_id]['allocated_qty_sum'] += allocated_qty
            # Set B: Available batches - only include if released_available > 0
            elif released_available > 0:
                warehouse_groups[warehouse_id]['available_batches'].append(batch)
            # Do NOT include: batches with released_available <= 0 that are NOT allocated
        
        # ALL warehouses are kept - do not filter out warehouses with only allocated batches!
        
        # STEP 2: Sort batches WITHIN each warehouse using FEFO/FIFO rules
        for warehouse_id, wh_data in warehouse_groups.items():
            # Sort allocated batches (Set A) - skip availability filter, must always show
            wh_data['allocated_batches'] = BatchAllocationService.sort_batches_for_drawer(
                wh_data['allocated_batches'],
                item,
                skip_availability_filter=True  # CRITICAL: Don't filter out zero-available allocated batches
            )
            # Sort available batches (Set B) - apply availability filter
            wh_data['available_batches'] = BatchAllocationService.sort_batches_for_drawer(
                wh_data['available_batches'],
                item,
                skip_availability_filter=False  # Filter out zero-available batches from Set B
            )
        
        # STEP 3: Per-Warehouse Truncation
        # Build limited batch list with per-warehouse truncation logic
        limited_batches = []
        
        for warehouse_id, wh_data in warehouse_groups.items():
            # STEP 3.1: Always include ALL allocated batches from this warehouse (Set A)
            # These are ALWAYS shown, even if available <= 0
            for batch in wh_data['allocated_batches']:
                limited_batches.append(batch)
            
            # STEP 3.2: Initialize potentialFromWarehouse with ALLOCATED quantities (not available)
            # This is the sum of allocated quantities from current_allocations for this warehouse
            potential_from_warehouse = wh_data['allocated_qty_sum']
            
            # STEP 3.3: Add available-only batches (Set B) until potential >= requested_qty
            for batch in wh_data['available_batches']:
                # Stop adding if this warehouse can already fulfill the entire request
                # using allocated quantities + previously added available batches
                if potential_from_warehouse >= requested_qty:
                    break
                
                # Add this available batch
                limited_batches.append(batch)
                # Use the pre-calculated released availability for consistency
                available_qty = batch._released_available
                # Add the available quantity to potential
                potential_from_warehouse += available_qty
        
        # STEP 4: Calculate total available and shortfall
        cumulative_available = Decimal('0')
        for batch in limited_batches:
            # Use the pre-calculated released availability for consistency
            available_qty = batch._released_available
            # Only count positive quantities (allocated batches may have zero or negative available)
            cumulative_available += max(Decimal('0'), available_qty)
        
        # Shortfall is the difference between requested and what's actually available
        shortfall = max(Decimal('0'), requested_qty - cumulative_available)
        
        return limited_batches, cumulative_available, shortfall
    
    @staticmethod
    def assign_priority_groups(batches: List[ItemBatch], item: Item) -> List[Tuple[ItemBatch, int]]:
        """
        Assign priority group IDs to batches based on FEFO/FIFO rules.
        Batches in the same priority group have the same expiry_date and batch_date.
        
        Args:
            batches: Sorted list of batches
            item: Item with issuance order configuration
            
        Returns:
            List of (batch, priority_group_id) tuples
        """
        if not batches:
            return []
        
        batch_groups = []
        current_group_id = 0
        prev_key = None
        
        for batch in batches:
            # Define priority key based on issuance order
            if item.issuance_order == 'FEFO' and item.can_expire_flag:
                current_key = (batch.expiry_date, batch.batch_date)
            else:  # FIFO or LIFO
                current_key = (batch.batch_date,)
            
            # Increment group ID if key changed
            if prev_key is not None and current_key != prev_key:
                current_group_id += 1
            
            batch_groups.append((batch, current_group_id))
            prev_key = current_key
        
        return batch_groups
