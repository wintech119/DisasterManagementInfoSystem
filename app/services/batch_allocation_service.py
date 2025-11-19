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
        allocated_qty: Decimal
    ) -> Tuple[bool, str]:
        """
        Validate a batch allocation.
        
        Args:
            batch_id: Batch ID to allocate from
            item_id: Item being allocated
            allocated_qty: Quantity to allocate
            
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
        available_qty = batch.usable_qty - batch.reserved_qty
        if allocated_qty > available_qty:
            return False, f'Batch {batch.batch_no} has only {available_qty} available, cannot allocate {allocated_qty}'
        
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
        remaining_qty: Decimal,
        required_uom: str = None,
        allocated_batch_ids: List[int] = None
    ) -> Tuple[List[ItemBatch], Decimal, Decimal]:
        """
        Get batches for the drawer display with global FEFO/FIFO ordering.
        Shows batches in FEFO order across all warehouses until cumulative quantity
        meets remaining_qty. Always includes previously allocated batches for editing.
        
        Args:
            item_id: Item ID
            remaining_qty: Remaining quantity to fulfill
            required_uom: Required unit of measure
            allocated_batch_ids: List of batch IDs that are already allocated (for editing)
            
        Returns:
            Tuple of:
                - List of batches (FEFO ordered + allocated)
                - Total available from these batches
                - Shortfall (0 if can fulfill, positive if not)
        """
        # Get item and all available batches
        item = Item.query.get(item_id)
        if not item:
            return [], Decimal('0'), remaining_qty
        
        batches = BatchAllocationService.get_available_batches(item_id, required_uom=required_uom)
        sorted_batches = BatchAllocationService.sort_batches_by_allocation_rule(batches, item)
        
        allocated_batch_ids = allocated_batch_ids or []
        
        # Separate allocated batches from available batches
        allocated_batches = []
        available_batches = []
        
        for batch in sorted_batches:
            if batch.batch_id in allocated_batch_ids:
                allocated_batches.append(batch)
            else:
                available_batches.append(batch)
        
        # Take batches in FEFO order until cumulative qty >= remaining_qty
        # This preserves global FEFO order across all warehouses
        limited_batches = []
        cumulative_qty = Decimal('0')
        
        for batch in available_batches:
            available_qty = batch.usable_qty - batch.reserved_qty
            limited_batches.append(batch)
            cumulative_qty += available_qty
            
            # Stop when we have enough to fulfill the request
            if cumulative_qty >= remaining_qty:
                break
        
        # Combine allocated batches with limited batches (deduplicating by batch_id)
        # Allocated batches must always be shown for editing
        seen_batch_ids = set()
        all_batches = []
        
        # First, add all allocated batches
        for batch in allocated_batches:
            all_batches.append(batch)
            seen_batch_ids.add(batch.batch_id)
        
        # Then add limited batches (skip if already in allocated)
        for batch in limited_batches:
            if batch.batch_id not in seen_batch_ids:
                all_batches.append(batch)
                seen_batch_ids.add(batch.batch_id)
        
        # Re-sort to ensure FEFO ordering (allocated batches may break order)
        all_batches = BatchAllocationService.sort_batches_by_allocation_rule(all_batches, item)
        
        # Calculate total available and shortfall
        cumulative_available = Decimal('0')
        for batch in all_batches:
            available_qty = batch.usable_qty - batch.reserved_qty
            cumulative_available += available_qty
        
        shortfall = max(Decimal('0'), remaining_qty - cumulative_available)
        
        return all_batches, cumulative_available, shortfall
    
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
