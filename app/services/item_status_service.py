"""
Item Status Service
Handles relief request item status validation and allowed status computation
"""
from decimal import Decimal
from typing import Dict, List, Tuple
from app.db import db
from app.db.models import ReliefRqstItemStatus

# Cache for active status lookup
_status_cache = None

def clear_status_cache():
    """Clear the status cache to force reload from database"""
    global _status_cache
    _status_cache = None

def load_status_map(force_reload: bool = False) -> Dict[str, Dict[str, str]]:
    """
    Load and cache active relief request item statuses
    
    Args:
        force_reload: If True, clears cache and reloads from database
    
    Returns: {status_code: {'desc': str, 'qty_rule': str}}
    """
    global _status_cache
    
    if force_reload:
        clear_status_cache()
    
    if _status_cache is None:
        statuses = ReliefRqstItemStatus.query.filter_by(active_flag=True).all()
        _status_cache = {
            s.status_code: {
                'desc': s.status_desc,
                'qty_rule': s.item_qty_rule
            }
            for s in statuses
        }
    
    return _status_cache

def compute_allowed_statuses(current_status: str, total_allocated: Decimal, requested_qty: Decimal) -> Tuple[str, List[str]]:
    """
    Compute allowed status options based on allocation state and current status.
    
    Args:
        current_status: Current item status code
        total_allocated: Total quantity allocated across all warehouses
        requested_qty: Requested quantity for the item
    
    Returns:
        Tuple of (auto_status, allowed_status_codes)
        - auto_status: Automatically determined status based on allocation
        - allowed_status_codes: List of status codes that can be manually selected
    
    Rules:
        - allocated == 0: auto=R, allowed={R, D, U, W}
        - 0 < allocated < requested: auto=P, allowed={P, L}
        - allocated >= requested: auto=F, allowed={F} (locked)
    """
    status_map = load_status_map()
    
    # Determine auto status based on allocation
    if total_allocated == Decimal('0'):
        auto_status = 'R'  # Requested
        # When zero allocated, can only select denial/unavailability statuses
        allowed_statuses = ['R', 'D', 'U', 'W']
    elif total_allocated >= requested_qty:
        auto_status = 'F'  # Filled
        # When fully allocated, status is locked to Filled
        allowed_statuses = ['F']
    else:
        auto_status = 'P'  # Partly filled
        # When partially allocated, can only mark as Partly Filled or Allowed Limit
        allowed_statuses = ['P', 'L']
    
    # Filter to only active statuses that exist in the database
    allowed_statuses = [s for s in allowed_statuses if s in status_map]
    
    return auto_status, allowed_statuses

def validate_status_transition(
    item_id: int,
    current_status: str,
    new_status: str,
    total_allocated: Decimal,
    requested_qty: Decimal
) -> Tuple[bool, str]:
    """
    Validate if a status transition is allowed based on allocation state.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    auto_status, allowed_statuses = compute_allowed_statuses(
        current_status, total_allocated, requested_qty
    )
    
    if new_status not in allowed_statuses:
        status_map = load_status_map()
        current_desc = status_map.get(current_status, {}).get('desc', current_status)
        new_desc = status_map.get(new_status, {}).get('desc', new_status)
        
        if total_allocated == Decimal('0'):
            return False, f"Item #{item_id}: With zero allocation, status must be one of: Requested, Denied, Unavailable, or Awaiting Availability (not {new_desc})"
        elif total_allocated >= requested_qty:
            return False, f"Item #{item_id}: Fully allocated items cannot change status from Filled"
        else:
            return False, f"Item #{item_id}: Partially allocated items can only be marked as Partly Filled or Allowed Limit (not {new_desc})"
    
    return True, ""

def validate_quantity_limit(
    item_id: int,
    total_allocated: Decimal,
    requested_qty: Decimal
) -> Tuple[bool, str]:
    """
    Validate that total allocation does not exceed requested quantity.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if total_allocated > requested_qty:
        return False, f"Item #{item_id}: Total allocated ({total_allocated}) exceeds requested quantity ({requested_qty})"
    
    return True, ""

def get_status_label(status_code: str) -> str:
    """Get human-readable label for a status code"""
    status_map = load_status_map()
    return status_map.get(status_code, {}).get('desc', status_code)
