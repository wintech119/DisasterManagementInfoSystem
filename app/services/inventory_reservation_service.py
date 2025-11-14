"""
Inventory Reservation Service

Manages inventory reservations during package preparation to prevent
double-allocation across concurrent package fulfillment operations.

Key Functions:
- reserve_inventory(): Updates reserved_qty when saving draft allocations
- release_inventory(): Releases reserved_qty when canceling or abandoning
- commit_inventory(): Converts reservations to actual deductions on dispatch
"""

from decimal import Decimal
from typing import List, Dict, Tuple
from sqlalchemy.exc import SQLAlchemyError
from app.db import db
from app.db.models import Inventory, ReliefPkgItem


def get_current_reservations(reliefrqst_id: int) -> Dict[Tuple[int, int], Decimal]:
    """
    Get current inventory reservations for a relief request.
    
    Returns: {(item_id, warehouse_id): reserved_qty}
    """
    pkg_items = ReliefPkgItem.query.filter_by(reliefrqst_id=reliefrqst_id).all()
    
    reservations = {}
    for pkg_item in pkg_items:
        if pkg_item.issue_qty and pkg_item.issue_qty > 0:
            key = (pkg_item.item_id, pkg_item.warehouse_id)
            reservations[key] = pkg_item.issue_qty
    
    return reservations


def reserve_inventory(reliefrqst_id: int, new_allocations: List[Dict]) -> Tuple[bool, str]:
    """
    Reserve inventory for package allocations.
    
    Updates reserved_qty in inventory table based on difference between
    current and new allocations. Validates that reservations don't exceed
    available inventory.
    
    Args:
        reliefrqst_id: Relief request ID
        new_allocations: List of {item_id, warehouse_id, allocated_qty}
    
    Returns:
        (success, error_message)
    """
    try:
        # Get current reservations from database
        current_reservations = get_current_reservations(reliefrqst_id)
        
        # Build new reservations map
        new_reservations = {}
        for alloc in new_allocations:
            if alloc['allocated_qty'] > 0:
                key = (alloc['item_id'], alloc['warehouse_id'])
                new_reservations[key] = alloc['allocated_qty']
        
        # Calculate differences and update inventory
        all_keys = set(current_reservations.keys()) | set(new_reservations.keys())
        
        for key in all_keys:
            item_id, warehouse_id = key
            current_qty = current_reservations.get(key, Decimal('0'))
            new_qty = new_reservations.get(key, Decimal('0'))
            difference = new_qty - current_qty
            
            if difference != 0:
                # Update inventory reserved_qty
                inventory = Inventory.query.filter_by(
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    status_code='A'
                ).with_for_update().first()
                
                if not inventory:
                    return False, f'No active inventory found for item {item_id} at warehouse {warehouse_id}'
                
                # Calculate new reserved quantity
                new_reserved = inventory.reserved_qty + difference
                
                # Validate: reserved_qty + difference must not exceed usable_qty
                if new_reserved < 0:
                    return False, f'Cannot release {abs(difference)} units - only {inventory.reserved_qty} reserved'
                
                if new_reserved > inventory.usable_qty:
                    available = inventory.usable_qty - inventory.reserved_qty
                    return False, f'Cannot reserve {difference} units at warehouse {inventory.warehouse.warehouse_name} - only {available} available'
                
                # Update reserved quantity
                inventory.reserved_qty = new_reserved
        
        return True, ''
        
    except SQLAlchemyError as e:
        db.session.rollback()
        return False, f'Database error during reservation: {str(e)}'


def release_all_reservations(reliefrqst_id: int) -> Tuple[bool, str]:
    """
    Release all inventory reservations for a relief request.
    
    Called when:
    - User cancels package preparation
    - Lock expires without saving
    - Package is abandoned
    
    Args:
        reliefrqst_id: Relief request ID
    
    Returns:
        (success, error_message)
    """
    try:
        current_reservations = get_current_reservations(reliefrqst_id)
        
        for (item_id, warehouse_id), reserved_qty in current_reservations.items():
            if reserved_qty > 0:
                inventory = Inventory.query.filter_by(
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    status_code='A'
                ).with_for_update().first()
                
                if inventory:
                    inventory.reserved_qty = max(Decimal('0'), inventory.reserved_qty - reserved_qty)
        
        return True, ''
        
    except SQLAlchemyError as e:
        db.session.rollback()
        return False, f'Database error during release: {str(e)}'


def commit_inventory(reliefrqst_id: int) -> Tuple[bool, str]:
    """
    Commit inventory allocations on package dispatch.
    
    Converts reservations to actual deductions:
    - Decreases usable_qty by allocated amounts
    - Decreases reserved_qty by allocated amounts
    
    Called when Logistics Manager sends package for dispatch.
    
    Args:
        reliefrqst_id: Relief request ID
    
    Returns:
        (success, error_message)
    """
    try:
        current_reservations = get_current_reservations(reliefrqst_id)
        
        for (item_id, warehouse_id), allocated_qty in current_reservations.items():
            if allocated_qty > 0:
                inventory = Inventory.query.filter_by(
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    status_code='A'
                ).with_for_update().first()
                
                if not inventory:
                    return False, f'No active inventory found for item {item_id} at warehouse {warehouse_id}'
                
                # Validate sufficient usable quantity
                if inventory.usable_qty < allocated_qty:
                    return False, f'Insufficient inventory at warehouse {inventory.warehouse.warehouse_name}: need {allocated_qty}, have {inventory.usable_qty}'
                
                # Commit allocation: decrease both usable and reserved
                inventory.usable_qty -= allocated_qty
                inventory.reserved_qty = max(Decimal('0'), inventory.reserved_qty - allocated_qty)
        
        return True, ''
        
    except SQLAlchemyError as e:
        db.session.rollback()
        return False, f'Database error during commit: {str(e)}'
