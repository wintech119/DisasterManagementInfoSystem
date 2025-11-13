"""
Role-Based Access Control (RBAC) utilities
"""
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user
from app.db import db
from sqlalchemy import text


def role_required(*role_codes):
    """
    Decorator to restrict access to routes based on user roles.
    
    Usage:
        @role_required('LOGISTICS_MANAGER', 'SYSTEM_ADMINISTRATOR')
        def my_route():
            ...
    
    Args:
        *role_codes: One or more role codes that are allowed to access the route
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            
            user_role_codes = [role.code for role in current_user.roles]
            
            if not any(code in user_role_codes for code in role_codes):
                flash('You do not have permission to access this page.', 'danger')
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def has_role(*role_codes):
    """
    Check if the current user has any of the specified roles.
    
    Usage in templates:
        {% if has_role('LOGISTICS_MANAGER', 'SYSTEM_ADMINISTRATOR') %}
            <a href="#">Admin Link</a>
        {% endif %}
    
    Args:
        *role_codes: One or more role codes to check
        
    Returns:
        bool: True if user has any of the specified roles
    """
    if not current_user.is_authenticated:
        return False
    
    user_role_codes = [role.code for role in current_user.roles]
    return any(code in user_role_codes for code in role_codes)


def has_all_roles(*role_codes):
    """
    Check if the current user has ALL of the specified roles.
    
    Args:
        *role_codes: One or more role codes to check
        
    Returns:
        bool: True if user has all of the specified roles
    """
    if not current_user.is_authenticated:
        return False
    
    user_role_codes = [role.code for role in current_user.roles]
    return all(code in user_role_codes for code in role_codes)


def agency_user_required(f):
    """
    Decorator to restrict access to agency users only.
    Ensures current_user has an agency_id set.
    
    Usage:
        @agency_user_required
        def my_route():
            # Only accessible to users with agency_id
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        
        if not current_user.agency_id:
            flash('This page is only accessible to agency users.', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def is_agency_user():
    """
    Check if the current user is an agency user (has agency_id set).
    
    Returns:
        bool: True if user is authenticated and has agency_id
    """
    if not current_user.is_authenticated:
        return False
    return current_user.agency_id is not None


def has_warehouse_access(warehouse_id):
    """
    Check if the current user has access to a specific warehouse.
    
    Args:
        warehouse_id: The warehouse ID to check
        
    Returns:
        bool: True if user has access to the warehouse
    """
    if not current_user.is_authenticated:
        return False
    
    if has_role('SYSTEM_ADMINISTRATOR', 'LOGISTICS_MANAGER'):
        return True
    
    user_warehouse_ids = [w.warehouse_id for w in current_user.warehouses]
    return warehouse_id in user_warehouse_ids


def get_user_role_codes():
    """
    Get a list of role codes for the current user.
    
    Returns:
        list: List of role code strings
    """
    if not current_user.is_authenticated:
        return []
    
    return [role.code for role in current_user.roles]


def get_user_role_names():
    """
    Get a list of role names for the current user.
    
    Returns:
        list: List of role name strings
    """
    if not current_user.is_authenticated:
        return []
    
    return [role.name for role in current_user.roles]


def is_admin():
    """
    Check if the current user is a system administrator.
    
    Returns:
        bool: True if user is an admin
    """
    return has_role('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')


def is_logistics_manager():
    """
    Check if the current user is a logistics manager.
    
    Returns:
        bool: True if user is a logistics manager
    """
    return has_role('LOGISTICS_MANAGER')


def is_logistics_officer():
    """
    Check if the current user is a logistics officer.
    
    Returns:
        bool: True if user is a logistics officer
    """
    return has_role('LOGISTICS_OFFICER')


def is_director_level():
    """
    Check if the current user is a director-level ODPEM executive.
    Only Director General, Deputy Director General, and Director PEOD.
    
    Returns:
        bool: True if user is director-level
    """
    return has_role('ODPEM_DG', 'ODPEM_DDG', 'ODPEM_DIR_PEOD')


def can_manage_users():
    """
    Check if the current user can manage users.
    
    Returns:
        bool: True if user can manage users
    """
    return has_role('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')


def can_view_reports():
    """
    Check if the current user can view reports.
    
    Returns:
        bool: True if user can view reports
    """
    return current_user.is_authenticated


def has_permission(resource, action):
    """
    Check if the current user has a specific permission based on their roles.
    
    Args:
        resource: The resource name (e.g., 'reliefrqst', 'inventory')
        action: The action name (e.g., 'approve_eligibility', 'view_all')
        
    Returns:
        bool: True if user has the permission
    """
    if not current_user.is_authenticated:
        return False
    
    # Get user's role IDs
    user_role_ids = [role.id for role in current_user.roles]
    
    if not user_role_ids:
        return False
    
    # Use SQLAlchemy ORM instead of raw SQL for database compatibility
    from app.db.models import Permission, RolePermission
    
    # Query for permission through role_permission join using ORM
    permission_count = db.session.query(Permission).join(
        RolePermission, Permission.perm_id == RolePermission.perm_id
    ).filter(
        RolePermission.role_id.in_(user_role_ids),
        Permission.resource == resource,
        Permission.action == action
    ).count()
    
    return permission_count > 0


def permission_required(resource, action):
    """
    Decorator to restrict access to routes based on permissions.
    
    Usage:
        @permission_required('reliefrqst', 'approve_eligibility')
        def my_route():
            ...
    
    Args:
        resource: The resource name (e.g., 'reliefrqst')
        action: The action name (e.g., 'approve_eligibility')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            
            if not has_permission(resource, action):
                flash('You do not have permission to perform this action.', 'danger')
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
