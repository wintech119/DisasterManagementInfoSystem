"""
Audit field helpers for DRIMS
All aidmgmt-3.sql tables require audit fields on insert/update
"""
from datetime import datetime

def add_audit_fields(obj, user_id, is_new=True):
    """
    Add or update audit fields on a model object
    
    Args:
        obj: SQLAlchemy model instance
        user_id: Current user ID (username or email) - will be converted to UPPERCASE per schema requirements
        is_new: True if creating new record, False if updating
    """
    now = datetime.now()
    # Truncate user_id to 20 characters to match database constraint (varchar(20))
    user_id_upper = user_id.upper()[:20]
    
    if is_new:
        if hasattr(obj, 'create_by_id'):
            obj.create_by_id = user_id_upper
        if hasattr(obj, 'create_dtime'):
            obj.create_dtime = now
        if hasattr(obj, 'version_nbr'):
            obj.version_nbr = 1
    
    if hasattr(obj, 'update_by_id'):
        obj.update_by_id = user_id_upper
    if hasattr(obj, 'update_dtime'):
        obj.update_dtime = now
    if hasattr(obj, 'version_nbr') and not is_new:
        obj.version_nbr += 1
    
    return obj

def add_verify_fields(obj, user_id):
    """Add verification audit fields - UPPERCASE enforced per schema"""
    now = datetime.now()
    # Truncate user_id to 20 characters to match database constraint (varchar(20))
    user_id_upper = user_id.upper()[:20]
    
    if hasattr(obj, 'verify_by_id'):
        obj.verify_by_id = user_id_upper
    if hasattr(obj, 'verify_dtime'):
        obj.verify_dtime = now
    
    return obj
